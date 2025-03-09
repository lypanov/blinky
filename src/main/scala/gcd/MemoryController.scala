package gcd

import chisel3._
import chisel3.util._

// Controller for CPU memory access 
class MemoryController(val useRealGowin: Boolean = true) extends Module {
  val io = IO(new Bundle {
    // CPU memory interface
    val cpuAddr = Input(UInt(32.W))
    val cpuWriteData = Input(UInt(32.W))
    val cpuWrite = Input(Bool())
    val cpuRead = Input(Bool())
    val cpuReadData = Output(UInt(32.W))
  })
  
  // Map CPU address to RAM - for now we'll just use the lower 6 bits
  // which gives access to our 64 words of memory
  val ramAddr = io.cpuAddr(7, 2)  // Get word address (bits 7:2)
  
  // Create appropriate RAM module based on parameter
  val ram: RAMInterface = if (useRealGowin) Module(new GowinSP()) else Module(new MockGowinSP())
  
  // Connect RAM signals
  ram.io.clk := clock
  ram.io.ce := io.cpuRead || io.cpuWrite
  ram.io.reset := false.B
  ram.io.wre := io.cpuWrite
  ram.io.ad := ramAddr(5, 0)
  ram.io.din := io.cpuWriteData
  ram.io.oce := true.B
  
  // Connect read data back to CPU
  io.cpuReadData := ram.io.dout
  
  // Debug output
  when (io.cpuRead) {
    printf(p"Memory Read: addr=${io.cpuAddr}, RAM addr=${ramAddr}\n")
  }
  when (io.cpuWrite) {
    printf(p"Memory Write: addr=${io.cpuAddr}, data=${io.cpuWriteData}, RAM addr=${ramAddr}\n")
  }
} 