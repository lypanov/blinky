package gcd

import chisel3._
import chisel3.experimental.{Analog, attach}
import chisel3.util._

// BlackBox wrapper for Gowin Single-Port RAM
class GowinSP extends BlackBox with HasBlackBoxInline {
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
  
  // Override the module name to match exactly what Gowin expects
  override def desiredName = "Gowin_SP"
} 