package gcd

import chisel3._

/** Forces the board LED off while a UART "pressed" latch is set.
 *
 *  Sits after the CPU LED register: `cpuLed` keeps toggling and the core
 *  keeps fetching. The pin is `cpuLed` when released and 0 when pressed, so
 *  a release resumes in whatever phase the register is already in.
 *
 *  Line is 8N1, 115200 baud, 27 MHz (Nano 4K PLL bypass and Primer 20K H11).
 *  Press: 0x01, ASCII '1', or space (0x20). Release: 0x00 or ASCII '0'.
 *  Any other byte leaves the latch alone.
 */
class UartLedGate(clkMHz: Int = 27, baud: Int = 115200) extends Module {
  val io = IO(new Bundle {
    val cpuLed = Input(Bool())
    val uartRx = Input(Bool())
    val led = Output(Bool())
    val pressed = Output(Bool())
  })

  val uartRx = Module(new UartRx(clkMHz, baud))
  uartRx.io.clk := clock
  uartRx.io.rst_n := ~reset.asBool
  uartRx.io.rx_pin := io.uartRx
  uartRx.io.rx_data_ready := true.B

  val pressed = RegInit(false.B)
  when(uartRx.io.rx_data_valid) {
    val b = uartRx.io.rx_data
    when(b === 0x01.U || b === 0x31.U || b === 0x20.U) {
      pressed := true.B
    }.elsewhen(b === 0x00.U || b === 0x30.U) {
      pressed := false.B
    }
  }

  io.pressed := pressed
  // Active-high CPU LED. Pressed forces the pin off; the register is untouched.
  io.led := io.cpuLed && !pressed
}
