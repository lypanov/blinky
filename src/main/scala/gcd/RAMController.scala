package gcd

import chisel3._
import chisel3.util._

// Module to encapsulate RAM access
class RAMController extends Module {
  val io = IO(new Bundle {
    // Simple interface that just exposes the lower 16 bits of the RAM value
    val value = Output(UInt(16.W))  // Reduced to 16 bits
  })
  
  // Instantiate the Gowin Single-Port RAM
  val ram = Module(new GowinSP())
  
  // Connect RAM signals
  ram.io.clk := clock
  ram.io.ce := true.B  // Clock enable always active
  ram.io.reset := false.B  // Reset permanently disabled
  ram.io.wre := false.B  // Write enable permanently disabled (read only)
  ram.io.ad := 0.U(6.W)  // Always use address 0
  ram.io.din := 0.U(32.W)  // No writing, so this doesn't matter
  ram.io.oce := true.B  // Output clock enable always active
  
  // Connect only the lower 16 bits of the RAM output to our simplified interface
  io.value := ram.io.dout(15, 0)  // Take only the lower 16 bits
} 