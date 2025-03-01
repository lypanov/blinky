package gcd

import chisel3._
import chisel3.util._

// Module to encapsulate RAM access
class RAMController extends Module {
  val io = IO(new Bundle {
    // Simple interface that exposes the RAM value and address counter
    val value = Output(UInt(16.W))  // Reduced to 16 bits
    val addr = Output(UInt(3.W))    // Expose the address counter
  })
  
  // Address counter that cycles from 0 to 7
  val addrCounter = RegInit(0.U(3.W))  // 3 bits to represent 0-7
  
  // Increment the counter on each clock cycle and wrap around at 7
  addrCounter := Mux(addrCounter === 7.U, 0.U, addrCounter + 1.U)
  
  // Connect address counter to output
  io.addr := addrCounter
  
  // Instantiate the Gowin Single-Port RAM
  val ram = Module(new GowinSP())
  
  // Connect RAM signals
  ram.io.clk := clock
  ram.io.ce := true.B  // Clock enable always active
  ram.io.reset := false.B  // Reset permanently disabled
  ram.io.wre := false.B  // Write enable permanently disabled (read only)
  ram.io.ad := addrCounter  // Use the cycling counter as address
  ram.io.din := 0.U(32.W)  // No writing, so this doesn't matter
  ram.io.oce := true.B  // Output clock enable always active
  
  // Connect only the lower 16 bits of the RAM output to our simplified interface
  io.value := ram.io.dout(15, 0)  // Take only the lower 16 bits
} 