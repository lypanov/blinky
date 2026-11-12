package gcd

import chisel3._
import _root_.circt.stage.ChiselStage
import java.io.File

/**
 * Simulation-only top: CPUSubset0 + mock RAM, no UART / Gowin IP.
 *
 * Does not change CPU behaviour. The disk bootstrap is the program.
 * A short even millisecond wait keeps a LED period observable.
 * Hardware uses the same linker with a 1000 ms wait.
 */
class CPUSimTop(
    programInstructions: Seq[String],
    customMemoryImage: Option[Seq[String]] = None,
    memBackend: String = "blockram",
    hyperFirstValid: Int = 12,
    bodyFetch: Boolean = false,
    core: Option[CoreMap] = None,
    flashBoot: Boolean = false,
    uartDisk: Boolean = false,
    // When set, the DDR3 command port is an IO. The Micron ddr3.v bench
    // drives it. The command-port stand-in is not instantiated.
    externalPhy: Boolean = false
) extends Module {
  val hyper = memBackend == "hyperram"
  val ddr3 = memBackend == "ddr3"
  val io = IO(new Bundle {
    val led = Output(Bool())
    val pc = Output(UInt(32.W))
    val halted = Output(Bool())
    val r0 = Output(UInt(32.W))
    val r1 = Output(UInt(32.W))
    val r2 = Output(UInt(32.W))
    val r3 = Output(UInt(32.W))
    val r5 = Output(UInt(32.W))
    val r9 = Output(UInt(32.W))
    val mask = Output(UInt(40.W))
    val memAddr = Output(UInt(32.W))
    val memWriteData = Output(UInt(32.W))
    val memWrite = Output(Bool())
    val memRead = Output(Bool())
    val spiCsN = Output(Bool())
    val spiClk = Output(Bool())
    val spiMosi = Output(Bool())
    val spiMiso = Input(Bool())
    val screenWe = Output(Bool())
    val bmpData = Output(UInt(32.W))
    val bmpWord = Output(UInt(13.W))
    // -84. Bits 8:0 of the store. The bench checks the bootstrap's
    // first store and Blink's mode bit. The video module is not in
    // this top; it samples the same pulse on the board.
    val statusWe = Output(Bool())
    val statusWord = Output(UInt(9.W))
    val diskValid = Input(Bool())
    val diskWord = Input(UInt(32.W))
    val diskTake = Output(Bool())
    val cpuClk = Output(Clock())
    val armed = Output(Bool())
    // Switch bit at -60. The bench's sampler drives it.
    val btnPressed = Input(Bool())
  })
  val phy = if (ddr3 && externalPhy) Some(IO(new Ddr3UserBundle)) else None

  // Modules fetch and register write miss 27 MHz. The CPU runs at half
  // the bridge clock, the same split the Dock uses for its command port.
  val cpuClock = if (ddr3) {
    val half = Module(new CpuClock)
    half.io.clk_in := clock
    half.io.clk_out
  } else if (hyper && core.isDefined) {
    val half = Module(new CpuClock2)
    half.io.clk_in := clock
    half.io.clk_out
  } else clock
  val cpu = withClock(cpuClock) { Module(new CPUSubset0(
    programInstructions,
    customMemoryImage = customMemoryImage,
    waitForStores = hyper || ddr3,
    bodyFetch = bodyFetch,
    core = core,
    flashBoot = flashBoot,
    uartDisk = uartDisk
  )) }
  io.cpuClk := cpuClock
  io.armed := cpu.io.armed
  cpu.io.btnPressed := io.btnPressed
  cpu.io.diskValid := io.diskValid
  cpu.io.diskWord := io.diskWord
  io.diskTake := cpu.io.diskTake
  io.spiCsN := cpu.io.spiCsN
  io.spiClk := cpu.io.spiClk
  io.spiMosi := cpu.io.spiMosi
  cpu.io.spiMiso := io.spiMiso
  if (hyper) {
    val bridge = Module(new HyperRamBridge)
    val model = Module(new HyperRamUserModel(hyperFirstValid))
    if (core.isDefined) {
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
  } else if (ddr3) {
    val bridge = Module(new Ddr3Bridge)
    val model = if (externalPhy) None else Some(Module(new Ddr3UserModel))
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
    if (externalPhy) {
      val port = phy.get
      port.rd := bridge.io.ddr.rd
      port.wr := bridge.io.ddr.wr
      port.refresh := bridge.io.ddr.refresh
      port.addr := bridge.io.ddr.addr
      port.din := bridge.io.ddr.din
      bridge.io.ddr.dout := port.dout
      bridge.io.ddr.data_ready := port.data_ready
      bridge.io.ddr.busy := port.busy
      bridge.io.ddr.calib := port.calib
    } else {
      val standin = model.get
      standin.io.clk := clock
      standin.io.rst_n := ~reset.asBool
      standin.io.rd := bridge.io.ddr.rd
      standin.io.wr := bridge.io.ddr.wr
      standin.io.refresh := bridge.io.ddr.refresh
      standin.io.addr := bridge.io.ddr.addr
      standin.io.din := bridge.io.ddr.din
      bridge.io.ddr.dout := standin.io.dout
      bridge.io.ddr.data_ready := standin.io.data_ready
      bridge.io.ddr.busy := standin.io.busy
      bridge.io.ddr.calib := standin.io.calib
    }
  } else {
    val memoryController = Module(new MemoryController(useRealGowin = false))
    memoryController.io.cpuAddr := cpu.io.memAddr
    memoryController.io.cpuWriteData := cpu.io.memWriteData
    memoryController.io.cpuWrite := cpu.io.memWrite
    memoryController.io.cpuRead := cpu.io.memRead
    cpu.io.memReadData := memoryController.io.cpuReadData
    cpu.io.memStall := false.B
  }

  io.led := cpu.io.led
  io.pc := cpu.io.pc
  io.halted := cpu.io.halted
  io.r0 := cpu.io.r0
  io.r1 := cpu.io.r1
  io.r2 := cpu.io.r2
  io.r3 := cpu.io.r3
  io.r5 := cpu.io.r5
  io.r9 := cpu.io.r9
  io.mask := cpu.io.dbgMask
  io.memAddr := cpu.io.memAddr
  io.memWriteData := cpu.io.memWriteData
  io.memWrite := cpu.io.memWrite
  io.memRead := cpu.io.memRead
  io.screenWe := cpu.io.screenWe
  io.bmpData := cpu.io.bmpData
  io.bmpWord := cpu.io.bmpWord
  io.statusWe := cpu.io.statusWe
  io.statusWord := cpu.io.statusWord
}

object CPUSimTop {
  private def getProjectRoot(): String = {
    Option(System.getenv("CHISEL_CPU_PROJECT_ROOT")).getOrElse {
      var current = new File(sys.props("user.dir"))
      while (current != null && !new File(current, "build.sc").exists() && !new File(current, "build.mill").exists()) {
        current = current.getParentFile
      }
      if (current != null) current.getAbsolutePath
      else sys.props("user.dir")
    }
  }

  def loadInstructionsFromFile(filePath: String): Seq[String] = {
    val source = scala.io.Source.fromFile(filePath)
    try {
      source.getLines()
        .map(_.trim)
        .filter(_.nonEmpty)
        .map(line => line.stripPrefix("0x"))
        .toSeq
    } finally {
      source.close()
    }
  }

  def main(args: Array[String]): Unit = {
    val projectRoot = getProjectRoot()
    val image = sys.env.getOrElse("SIM_IMAGE", "modules")
    val targetDir = "generated"
    new File(targetDir).mkdirs()

    val (gen, outFile, label) = image match {
      case "ddr3modules" =>
        val externalPhy = sys.env.getOrElse("DDR3_PHY", "") == "micron"
        val imemPath = new File(
          projectRoot,
          sys.env.getOrElse("BLINK3_IMEM", "sim/visualizer/imem/ddr3modules.words")
        ).getAbsolutePath
        val words = loadInstructionsFromFile(imemPath)
        val coreMap = Some(CoreMap.load(projectRoot).getOrElse(
          throw new RuntimeException("ddr3modules needs sim/visualizer/imem/core.map — run sim/link_inner.py")
        ))
        val uartDisk = coreMap.exists(_.uartDisk)
        if (!uartDisk) {
          throw new RuntimeException("ddr3modules needs the UART disk map")
        }
        println(s"CPUSimTop: ddr3modules IMEM ${words.length} words externalPhy=$externalPhy uartDisk=$uartDisk from $imemPath")
        (
          () => new CPUSimTop(
            Seq.empty,
            customMemoryImage = Some(words),
            memBackend = "ddr3",
            bodyFetch = true,
            core = coreMap,
            externalPhy = externalPhy,
            uartDisk = uartDisk
          ),
          s"$targetDir/CPUSimTopDdr3.v",
          image
        )
      case "modules" =>
        val imemPath = new File(
          projectRoot,
          sys.env.getOrElse("BLINK3_IMEM", "sim/visualizer/imem/modules.words")
        ).getAbsolutePath
        val words = loadInstructionsFromFile(imemPath)
        val firstValid = sys.env.get("HYPER_FIRST_VALID").map(_.toInt).getOrElse(13)
        val coreMap = Some(CoreMap.load(projectRoot).getOrElse(
          throw new RuntimeException("modules needs sim/visualizer/imem/core.map — run sim/link_inner.py")
        ))
        val uartDisk = coreMap.exists(_.uartDisk)
        val flashBoot = coreMap.exists(_.romWords <= 512) && !uartDisk
        if (!flashBoot && !uartDisk) {
          throw new RuntimeException("modules needs the NOR disk map or the UART disk map")
        }
        println(s"CPUSimTop: modules IMEM ${words.length} words from $imemPath")
        println(s"CPUSimTop: FIRST_VALID=$firstValid flashBoot=$flashBoot uartDisk=$uartDisk")
        (
          () => new CPUSimTop(
            Seq.empty,
            customMemoryImage = Some(words),
            memBackend = "hyperram",
            hyperFirstValid = firstValid,
            bodyFetch = true,
            core = coreMap,
            flashBoot = flashBoot,
            uartDisk = uartDisk
          ),
          s"$targetDir/CPUSimTopHyper.v",
          image
        )
      case other =>
        throw new RuntimeException(s"SIM_IMAGE=$other is retired. Use modules or ddr3modules.")
    }

    val verilog = ChiselStage.emitSystemVerilog(
      gen = gen(),
      firtoolOpts = Array(
        "-disable-all-randomization",
        "-strip-debug-info",
        "--lowering-options=disallowLocalVariables,disallowPackedArrays,noAlwaysComb"
      )
    )

    val writer = new java.io.PrintWriter(new File(outFile))
    writer.write(verilog)
    writer.close()
    println(s"Simulation Verilog ($label) written to $outFile")
  }
}
