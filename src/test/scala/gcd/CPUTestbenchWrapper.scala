package gcd

import chisel3._
import chisel3.util._

/**
 * A wrapper for the CPU that connects it to a memory controller for testing.
 * This is similar to CPUMinimalWrapper but designed specifically for test environments.
 */
class CPUTestbenchWrapper(instructionHexStrings: Seq[String] = Seq.empty[String]) extends Module {
  val io = IO(new Bundle {
    val r0 = Output(UInt(32.W))
    val r1 = Output(UInt(32.W)) 
    val r2 = Output(UInt(32.W))
    val r3 = Output(UInt(32.W))
    val cpuHalted = Output(Bool())
    val pc = Output(UInt(32.W))  // Expose the program counter
    
    // Expose memory interface signals for monitoring
    val memAddr = Output(UInt(32.W))
    val memWriteData = Output(UInt(32.W))
    val memWrite = Output(Bool())
    val memRead = Output(Bool())

    // UART interface
    val uart_rx = Input(Bool())
    val uart_tx = Output(Bool())
  })
  
  // Create CPU with the provided instructions
  val cpu = Module(new CPUSubset0(instructionHexStrings))
  
  // Create memory controller (use mock version for tests)
  val memoryController = Module(new MemoryController(useRealGowin = false))
  
  // Connect CPU to memory
  memoryController.io.cpuAddr := cpu.io.memAddr
  memoryController.io.cpuWriteData := cpu.io.memWriteData
  memoryController.io.cpuWrite := cpu.io.memWrite
  memoryController.io.cpuRead := cpu.io.memRead
  cpu.io.memReadData := memoryController.io.cpuReadData
  
  // Connect outputs
  io.r0 := cpu.io.r0
  io.r1 := cpu.io.r1
  io.r2 := cpu.io.r2
  io.r3 := cpu.io.r3
  io.cpuHalted := cpu.io.halted
  io.pc := cpu.io.pc  // Connect PC to the output

  val logger = Module(new Logger(numProducers = 1))
  logger.io.clk := clock
  logger.io.rst_n := ~reset.asBool
  logger.io.uart_rx := io.uart_rx
  io.uart_tx := logger.io.uart_tx
  
  logger.io.producerLogs(0) <> cpu.io.logOut
  // logger.io.producerLogs(1) <> memoryController.io.logOut
  
  // Connect memory interface signals to outputs for monitoring
  io.memAddr := cpu.io.memAddr
  io.memWriteData := cpu.io.memWriteData
  io.memWrite := cpu.io.memWrite
  io.memRead := cpu.io.memRead
} 