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
} 