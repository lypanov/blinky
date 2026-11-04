package gcd

import chisel3._
import chisel3.util._

class CPUMinimalWrapper(
    useRealGowin: Boolean = true,
    programInstructions: Seq[String] = Seq.empty[String],
    customMemoryImage: Option[Seq[String]] = None
) extends Module {
  val io = IO(new Bundle {
    val led = Output(Bool())         // LED output
    val deadbeef = Output(UInt(16.W)) // RAM value
    val addr = Output(UInt(3.W))     // Address counter
    val uart_rx = Input(Bool())      // UART receive pin
    val uart_tx = Output(Bool())     // UART transmit pin
  })
  
  // Blink2 uses the small default IMEM (programInstructions). Blink3 passes
  // the linked image + address-0 BL trampoline as customMemoryImage.
  val cpu = Module(new CPUSubset0(programInstructions, customMemoryImage = customMemoryImage))
  io.led := cpu.io.led
  
  // Use the abstracted RAM controller for cycling display
  val ramController = Module(new RAMController(useRealGowin))
  
  // Create a memory controller for CPU access
  val memoryController = Module(new MemoryController(useRealGowin))
  
  // Connect the CPU memory interface to our memory controller
  memoryController.io.cpuAddr := cpu.io.memAddr
  memoryController.io.cpuWriteData := cpu.io.memWriteData
  memoryController.io.cpuWrite := cpu.io.memWrite
  memoryController.io.cpuRead := cpu.io.memRead
  cpu.io.memReadData := memoryController.io.cpuReadData
  
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