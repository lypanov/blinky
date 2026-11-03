package gcd

import chisel3._
import chisel3.util._

// Common interface for RAM modules (both real and mock)
trait RAMInterface {
  // Define the common I/O bundle that both implementations must have
  val io: Bundle {
    val dout: UInt
    val clk: Clock
    val oce: Bool
    val ce: Bool
    val reset: Bool
    val wre: Bool
    val ad: UInt
    val din: UInt
  }
} 