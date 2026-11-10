package gcd

import chisel3._
import chisel3.util._

class CpuWrapBase extends Bundle {
  val led = Output(Bool())
  val deadbeef = Output(UInt(16.W))
  val addr = Output(UInt(3.W))
  val uart_rx = Input(Bool())
  val uart_tx = Output(Bool())
}

class CpuWrapHyper extends CpuWrapBase {
  val hr = new HyperRamUserBundle
  // Modules image only. clk_out/2. The bridge stays on clock.
  val cpu_clock = Input(Clock())
  // External NOR. Idle unless this image is the flash bootstrap.
  val spi_cs_n = Output(Bool())
  val spi_clk = Output(Bool())
  val spi_mosi = Output(Bool())
  val spi_miso = Input(Bool())
  // -80. The top ties these to the screen only in square mode.
  val screen_we = Output(Bool())
  val screen_bit = Output(Bool())
  val armed = Output(Bool())
  // Switch bit at -60. The sampler outside this wrapper drives it.
  val btnPressed = Input(Bool())
}

class CpuWrapDdr3 extends CpuWrapBase {
  val ddr = new Ddr3UserBundle
  val cpu_clock = Input(Clock())
  val pc = Output(UInt(32.W))
  val r0 = Output(UInt(32.W))
  val r4 = Output(UInt(32.W))
  val r5 = Output(UInt(32.W))
  val r7 = Output(UInt(32.W))
  val r8 = Output(UInt(32.W))
  val r9 = Output(UInt(32.W))
  val dbgMask = Output(UInt(40.W))
  // -80. The Dock top ties these to the screen only in square mode.
  val screen_we = Output(Bool())
  val screen_bit = Output(Bool())
  val armed = Output(Bool())
  // UART word port. The Dock bootstrap loads disk.bin through these.
  val disk_valid = Input(Bool())
  val disk_word = Input(UInt(32.W))
  val disk_take = Output(Bool())
  // Switch bit at -60. The sampler outside this wrapper drives it.
  val btnPressed = Input(Bool())
}

class CPUMinimalWrapper(
    useRealGowin: Boolean = true,
    programInstructions: Seq[String] = Seq.empty[String],
    customMemoryImage: Option[Seq[String]] = None,
    memBackend: String = "blockram",
    hyperFirstValid: Int = 12,
    bodyFetch: Boolean = false,
    core: Option[CoreMap] = None,
    flashBoot: Boolean = false,
    uartDisk: Boolean = false,
    // DDR3 elaborations keep the Logger. Nano 4K images leave it out.
    // The Dock training UART is ddr3_uart_tx, not this module.
    enableLogger: Boolean = false
) extends Module {
  val hyper = memBackend == "hyperram"
  val ddr3 = memBackend == "ddr3"
  val exposeHyper = hyper && useRealGowin
  val exposeDdr = ddr3 && useRealGowin
  val io = IO(
    if (exposeHyper) new CpuWrapHyper
    else if (exposeDdr) new CpuWrapDdr3
    else new CpuWrapBase
  )
  
  // The disk bootstrap is customMemoryImage. Loads and stores stall on
  // HyperRAM and on DDR3. The DDR3 CPU is on pclk/4. The bridge stays on
  // pclk. The 4K CPU is on clk_out/2. The HyperRAM bridge stays on clk_out.
  val hyperSlow = hyper && useRealGowin && core.isDefined
  val cpuClock = if (ddr3 && useRealGowin) io.asInstanceOf[CpuWrapDdr3].cpu_clock
    else if (hyperSlow) io.asInstanceOf[CpuWrapHyper].cpu_clock
    else clock
  val cpuReset = if (hyperSlow) {
    withClock(cpuClock) {
      val s1 = RegInit(true.B)
      val s2 = RegInit(true.B)
      s1 := reset.asBool
      s2 := s1
      s2
    }
  } else reset
  val cpu = withClockAndReset(cpuClock, cpuReset) {
    Module(new CPUSubset0(
      programInstructions,
      customMemoryImage = customMemoryImage,
      waitForStores = hyper || ddr3,
      bodyFetch = bodyFetch,
      core = core,
      flashBoot = flashBoot,
      uartDisk = uartDisk
    ))
  }
  cpu.io.diskValid := false.B
  cpu.io.diskWord := 0.U
  cpu.io.btnPressed := false.B
  if (exposeHyper) {
    cpu.io.btnPressed := io.asInstanceOf[CpuWrapHyper].btnPressed
  }
  if (exposeDdr) {
    cpu.io.btnPressed := io.asInstanceOf[CpuWrapDdr3].btnPressed
  }
  if (exposeDdr) {
    val pins = io.asInstanceOf[CpuWrapDdr3]
    cpu.io.diskValid := pins.disk_valid
    cpu.io.diskWord := pins.disk_word
    pins.disk_take := cpu.io.diskTake
  }
  if (exposeHyper) {
    val pins = io.asInstanceOf[CpuWrapHyper]
    pins.spi_cs_n := cpu.io.spiCsN
    pins.spi_clk := cpu.io.spiClk
    pins.spi_mosi := cpu.io.spiMosi
    cpu.io.spiMiso := pins.spi_miso
    pins.screen_we := cpu.io.screenWe
    pins.screen_bit := cpu.io.screenBit
    pins.armed := cpu.io.armed
  } else {
    cpu.io.spiMiso := false.B
  }
  io.led := cpu.io.led
  
  // Use the abstracted RAM controller for cycling display
  val ramController = Module(new RAMController(useRealGowin))
  
  if (hyper) {
    val bridge = Module(new HyperRamBridge)
    if (core.isDefined && useRealGowin) {
      val cross = Module(new HyperReqCross)
      cross.io.cpuClock := cpuClock
      cross.io.bridgeBusy := bridge.io.memStall
      cross.io.inAddr := cpu.io.memAddr
      cross.io.inWriteData := cpu.io.memWriteData
      cross.io.inWrite := cpu.io.memWrite
      cross.io.inRead := cpu.io.memRead
      cross.io.inByte := cpu.io.memByte
      bridge.io.cpuAddr := cross.io.addr
      bridge.io.cpuWriteData := cross.io.writeData
      bridge.io.cpuWrite := cross.io.write
      bridge.io.cpuRead := cross.io.read
      bridge.io.cpuByte := cross.io.byte
      cpu.io.memReadData := bridge.io.cpuReadData
      val align = withClock(cpuClock) { Module(new Ddr3StallAlign) }
      align.io.req := cpu.io.memRead || cpu.io.memWrite
      align.io.bridgeStall := bridge.io.memStall
      cpu.io.memStall := align.io.stall
    } else {
      bridge.io.cpuAddr := cpu.io.memAddr
      bridge.io.cpuWriteData := cpu.io.memWriteData
      bridge.io.cpuWrite := cpu.io.memWrite
      bridge.io.cpuRead := cpu.io.memRead
      bridge.io.cpuByte := cpu.io.memByte
      cpu.io.memReadData := bridge.io.cpuReadData
      cpu.io.memStall := bridge.io.memStall
    }
    if (useRealGowin) {
      val hr = io.asInstanceOf[CpuWrapHyper].hr
      hr.cmd := bridge.io.hr.cmd
      hr.cmd_en := bridge.io.hr.cmd_en
      hr.addr := bridge.io.hr.addr
      hr.wr_data := bridge.io.hr.wr_data
      hr.data_mask := bridge.io.hr.data_mask
      bridge.io.hr.rd_data := hr.rd_data
      bridge.io.hr.rd_data_valid := hr.rd_data_valid
      bridge.io.hr.init_calib := hr.init_calib
    } else {
      val model = Module(new HyperRamUserModel(hyperFirstValid))
      model.io.clk := clock
      model.io.memory_clk := clock
      model.io.pll_lock := true.B
      model.io.rst_n := ~reset.asBool
      model.io.cmd := bridge.io.hr.cmd
      model.io.cmd_en := bridge.io.hr.cmd_en
      model.io.addr := bridge.io.hr.addr
      model.io.wr_data := bridge.io.hr.wr_data
      model.io.data_mask := bridge.io.hr.data_mask
      bridge.io.hr.rd_data := model.io.rd_data
      bridge.io.hr.rd_data_valid := model.io.rd_data_valid
      bridge.io.hr.init_calib := model.io.init_calib
    }
  } else if (ddr3) {
    val bridge = Module(new Ddr3Bridge)
    val sync = withClock(cpuClock) { Module(new Ddr3CpuPortSync) }
    sync.io.inAddr := cpu.io.memAddr
    sync.io.inWriteData := cpu.io.memWriteData
    sync.io.inWrite := cpu.io.memWrite
    sync.io.inRead := cpu.io.memRead
    sync.io.inByte := cpu.io.memByte
    bridge.io.cpuAddr := sync.io.addr
    bridge.io.cpuWriteData := sync.io.writeData
    bridge.io.cpuWrite := sync.io.write
    bridge.io.cpuRead := sync.io.read
    bridge.io.cpuByte := sync.io.byte
    cpu.io.memReadData := bridge.io.cpuReadData
    val align = withClock(cpuClock) { Module(new Ddr3StallAlign) }
    align.io.req := cpu.io.memRead || cpu.io.memWrite
    align.io.bridgeStall := bridge.io.memStall
    cpu.io.memStall := align.io.stall
    if (useRealGowin) {
      val wrap = io.asInstanceOf[CpuWrapDdr3]
      wrap.pc := cpu.io.pc
      wrap.r0 := cpu.io.r0
      wrap.r4 := cpu.io.r4
      wrap.r5 := cpu.io.r5
      wrap.r7 := cpu.io.r7
      wrap.r8 := cpu.io.r8
      wrap.r9 := cpu.io.r9
      wrap.dbgMask := cpu.io.dbgMask
      wrap.screen_we := cpu.io.screenWe
      wrap.screen_bit := cpu.io.screenBit
      wrap.armed := cpu.io.armed
    }
    if (useRealGowin) {
      val ddr = io.asInstanceOf[CpuWrapDdr3].ddr
      ddr.rd := bridge.io.ddr.rd
      ddr.wr := bridge.io.ddr.wr
      ddr.refresh := bridge.io.ddr.refresh
      ddr.addr := bridge.io.ddr.addr
      ddr.din := bridge.io.ddr.din
      bridge.io.ddr.dout := ddr.dout
      bridge.io.ddr.data_ready := ddr.data_ready
      bridge.io.ddr.busy := ddr.busy
      bridge.io.ddr.calib := ddr.calib
    } else {
      val model = Module(new Ddr3UserModel)
      model.io.clk := clock
      model.io.rst_n := ~reset.asBool
      model.io.rd := bridge.io.ddr.rd
      model.io.wr := bridge.io.ddr.wr
      model.io.refresh := bridge.io.ddr.refresh
      model.io.addr := bridge.io.ddr.addr
      model.io.din := bridge.io.ddr.din
      bridge.io.ddr.dout := model.io.dout
      bridge.io.ddr.data_ready := model.io.data_ready
      bridge.io.ddr.busy := model.io.busy
      bridge.io.ddr.calib := model.io.calib
    }
  } else {
    val memoryController = Module(new MemoryController(useRealGowin))
    memoryController.io.cpuAddr := cpu.io.memAddr
    memoryController.io.cpuWriteData := cpu.io.memWriteData
    memoryController.io.cpuWrite := cpu.io.memWrite
    memoryController.io.cpuRead := cpu.io.memRead
    cpu.io.memReadData := memoryController.io.cpuReadData
    cpu.io.memStall := false.B
  }
  
  // Connect cycling RAM controller to display output
  io.deadbeef := ramController.io.value
  io.addr := ramController.io.addr

  // The wrapper ports stay so both board tops keep the same UART pins.
  // On the 4K the pin is an idle mark and the Logger is not elaborated.
  if (enableLogger) {
    val logger = Module(new Logger())
    logger.io.clk := clock
    logger.io.rst_n := ~reset.asBool
    logger.io.uart_rx := io.uart_rx
    logger.io.messageCode := cpu.io.messageCode
    logger.io.trigger := cpu.io.trigger
    logger.io.logByte := cpu.io.logByte
    io.uart_tx := logger.io.uart_tx
  } else {
    dontTouch(io.uart_rx)
    io.uart_tx := true.B
  }
} 
