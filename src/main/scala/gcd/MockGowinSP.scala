package gcd

import chisel3._
import chisel3.util._

// Mock implementation of GowinSP for simulation purposes
class MockGowinSP extends Module with RAMInterface {
  val io = IO(new Bundle {
    val dout = Output(UInt(32.W))
    val clk = Input(Clock())
    val oce = Input(Bool())
    val ce = Input(Bool())
    val reset = Input(Bool())
    val wre = Input(Bool())
    val ad = Input(UInt(6.W))
    val din = Input(UInt(32.W))
  })
  
  // Create a small memory array for testing (64 entries, 32 bits each)
  val mem = RegInit(VecInit(Seq.tabulate(64) { i => 
    if (i < 8) {
      // Only for indices 0-7, use 0x0000BEEn pattern
      ("h0000BEE" + i.toHexString).U(32.W)
    } else {
      // All other memory locations are zeros
      0.U(32.W)
    }
  }))
  
  // Write logic
  when (io.ce && io.wre) {
    mem(io.ad) := io.din
  }
  
  // Read logic with 1-cycle delay on the output instead of the address
  // Immediately sample the memory at the current address and then register the value
  val dataOutReg = RegInit(0.U(32.W))
  when (io.ce && !io.wre) {
    dataOutReg := mem(io.ad)
  }
  
  // Apply output clock enable
  io.dout := Mux(io.oce, dataOutReg, 0.U)
} 