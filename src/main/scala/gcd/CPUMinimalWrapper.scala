package gcd

import chisel3._
import chisel3.util._

class CPUMinimalWrapper(useRealGowin: Boolean = true, programInstructions: Seq[String]) extends Module {
  val io = IO(new Bundle {
    val led = Output(Bool())         // LED output
    val deadbeef = Output(UInt(16.W)) // RAM value
    val addr = Output(UInt(3.W))     // Address counter
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
} 