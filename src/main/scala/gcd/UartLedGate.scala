package gcd

import chisel3._

/** Forces the board LED off while a button is held or a UART press is latched.
 *
 *  Sits after the CPU LED register: `cpuLed` keeps toggling and the core
 *  keeps fetching. The pin is `cpuLed` when released and 0 when pressed, so
 *  a release resumes in whatever phase the register is already in.
 *
 *  `btn_n` is active-low (Tang Nano 4K S1 / KEY1, pin 14: 100 kΩ to 1.8 V,
 *  switch to ground). It is synchronised. A board with no button ties it high.
 *
 *  UART is 8N1, 115200 baud, 27 MHz. Press: 0x01, ASCII '1', or space.
 *  Release: 0x00 or ASCII '0'. Any other byte leaves the UART latch alone.
 *  The pin is off if either source says pressed.
 */
class UartLedGate(clkMHz: Int = 27, baud: Int = 115200) extends Module {
  val io = IO(new Bundle {
    val cpuLed = Input(Bool())
    val uartRx = Input(Bool())
    val btn_n = Input(Bool())
    val led = Output(Bool())
    val pressed = Output(Bool())
  })

  val uartRx = Module(new UartRx(clkMHz, baud))
  uartRx.io.clk := clock
  uartRx.io.rst_n := ~reset.asBool
  uartRx.io.rx_pin := io.uartRx
  uartRx.io.rx_data_ready := true.B

  val uartLatch = RegInit(false.B)
  when(uartRx.io.rx_data_valid) {
    val b = uartRx.io.rx_data
    when(b === 0x01.U || b === 0x31.U || b === 0x20.U) {
      uartLatch := true.B
    }.elsewhen(b === 0x00.U || b === 0x30.U) {
      uartLatch := false.B
    }
  }

  val btnSync0 = RegInit(true.B)
  val btnSync1 = RegInit(true.B)
  btnSync0 := io.btn_n
  btnSync1 := btnSync0

  io.pressed := uartLatch || !btnSync1
  // Active-high CPU LED. Pressed forces the pin off; the register is untouched.
  io.led := io.cpuLed && !io.pressed
}
