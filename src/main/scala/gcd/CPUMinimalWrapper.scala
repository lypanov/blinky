package gcd

import chisel3._
import chisel3.util._

class CPUMinimalWrapper(useRealGowin: Boolean = true, programInstructions: Seq[String]) extends Module {
  val io = IO(new Bundle {
    val led = Output(Bool())         // LED output
    val deadbeef = Output(UInt(16.W)) // RAM value
    val addr = Output(UInt(3.W))     // Address counter
    val uart_rx = Input(Bool())      // UART receive pin
    val uart_tx = Output(Bool())     // UART transmit pin
  })
  
  // Internal CPU with the provided program instructions
  val cpu = Module(new CPUSubset0(programInstructions))
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

  // Create and properly initialize the UART transmitter
  /*
  val uartTx = Module(new UartTx())
  uartTx.io.clk := clock
  uartTx.io.rst_n := reset.asBool
  uartTx.io.tx_data := cpu.io.memWriteData(7, 0)  // Use bottom 8 bits of CPU write data
  uartTx.io.tx_data_valid := cpu.io.memWrite & (cpu.io.memAddr === "h1000".U)  // Map to memory address 0x1000
  io.uart_tx := uartTx.io.tx_pin
  */

  val uartTest = Module(new UartTest())
  uartTest.io.clk := clock
  uartTest.io.rst_n := reset.asBool
  uartTest.io.uart_rx := io.uart_rx
  uartTest.io.uart_tx := io.uart_tx
} 