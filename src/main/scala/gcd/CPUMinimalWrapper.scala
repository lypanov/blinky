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
}

class CPUMinimalWrapper(
    useRealGowin: Boolean = true,
    programInstructions: Seq[String] = Seq.empty[String],
    customMemoryImage: Option[Seq[String]] = None,
    memBackend: String = "blockram",
    hyperFirstValid: Int = 12,
    extraChecks: Int = 0,
    fetchStored: Boolean = false,
    chainFix: Boolean = false
) extends Module {
  val hyper = memBackend == "hyperram"
  val exposeHyper = hyper && useRealGowin
  val io = IO(if (exposeHyper) new CpuWrapHyper else new CpuWrapBase)
  
  // Blink2 uses the small default IMEM (programInstructions). Blink3 passes
  // the linked image + address-0 BL trampoline as customMemoryImage.
  // HyperRAM uses that image plus the walking-pattern prologue, and stalls
  // loads and stores. Block RAM keeps waitForStores false.
  val cpu = Module(new CPUSubset0(
    programInstructions,
    customMemoryImage = customMemoryImage,
    waitForStores = hyper,
    requireMemCheck = hyper,
    extraChecks = extraChecks,
    fetchStored = fetchStored,
    chainFix = chainFix
  ))
  io.led := cpu.io.led
  
  // Use the abstracted RAM controller for cycling display
  val ramController = Module(new RAMController(useRealGowin))
  
  if (hyper) {
    val bridge = Module(new HyperRamBridge)
    bridge.io.cpuAddr := cpu.io.memAddr
    bridge.io.cpuWriteData := cpu.io.memWriteData
    bridge.io.cpuWrite := cpu.io.memWrite
    bridge.io.cpuRead := cpu.io.memRead
    bridge.io.cpuByte := cpu.io.memByte
    cpu.io.memReadData := bridge.io.cpuReadData
    cpu.io.memStall := bridge.io.memStall
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

  // Create and properly initialize the Logger module
  val logger = Module(new Logger())
  logger.io.clk := clock
  logger.io.rst_n := ~reset.asBool
  logger.io.uart_rx := io.uart_rx
  logger.io.messageCode := cpu.io.messageCode
  logger.io.trigger := cpu.io.trigger
  logger.io.logByte := cpu.io.logByte
  io.uart_tx := logger.io.uart_tx
} 