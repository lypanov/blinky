package gcd

import chisel3._
import chisel3.util._

// Module to encapsulate RAM access
class RAMController(val useRealGowin: Boolean = true) extends Module {
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
  
  // Use the appropriate RAM implementation based on parameter
  val ramInterface = if (useRealGowin) {
    val ram = Module(new GowinSP())
    ram.io
  } else {
    val ram = Module(new MockGowinSP())
    ram.io
  }
  
  // Connect RAM signals
  ramInterface.clk := clock
  ramInterface.ce := true.B  // Clock enable always active
  ramInterface.reset := false.B  // Reset permanently disabled
  ramInterface.wre := false.B  // Write enable permanently disabled (read only)
  ramInterface.ad := addrCounter  // Use the cycling counter as address
  ramInterface.din := 0.U(32.W)  // No writing, so this doesn't matter
  ramInterface.oce := true.B  // Output clock enable always active
  
  // Connect only the lower 16 bits of the RAM output to our simplified interface
  io.value := ramInterface.dout(15, 0)  // Take only the lower 16 bits
} 