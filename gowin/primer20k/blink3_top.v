// Board wrapper for Blink3 on the Tang Primer 20K Dock (GW2A-18C).
// Clock is the 27 MHz oscillator on H11 (GCLK). No PLL: the wiki Dock
// blinky already proved H11 is a clean global clock at 1.000 Hz.
//
// Dock user LEDs are active-low (anode to 3V3 via 510R). CPU io_led is
// active-high, so invert onto L14 (wiki Orange_LED4). C13/A13 stay
// steadily lit so the webcam's 3-LED orange cluster (2 steady + 1
// blinker) still matches detect_leds. UART stays off-chip: do not steal
// BL702 M11/T13.
//
// SRAM-load only. Do not flash.

module blink3_top (
  input  Clock,
  output IO_voltage,
  output [4:0] led
);

  wire [15:0] unused_deadbeef;
  wire [2:0]  unused_addr;
  wire        cpu_led;
  wire        unused_uart_tx;

  // Short power-on reset, then run. No KEY: T10 is SSPI / FPGA_RST and
  // is shared with the SOM supervisor — leave it alone.
  reg [7:0] por = 8'hff;
  always @(posedge Clock) begin
    if (por != 8'h00)
      por <= por - 8'h01;
  end
  wire cpu_reset = (por != 8'h00);

  CPUMinimalWrapper u_cpu (
    .clock       (Clock),
    .reset       (cpu_reset),
    .io_led      (cpu_led),
    .io_deadbeef (unused_deadbeef),
    .io_addr     (unused_addr),
    .io_uart_rx  (1'b1),
    .io_uart_tx  (unused_uart_tx)
  );

  // L14: Blink3. Invert so CPU 1 = LED lit.
  assign IO_voltage = ~cpu_led;
  // C13 / A13: DONE / READY as GPIO, held on (active-low).
  assign led[0] = 1'b0;
  assign led[1] = 1'b0;
  // N16 / N14 / L16: off.
  assign led[2] = 1'b1;
  assign led[3] = 1'b1;
  assign led[4] = 1'b1;

endmodule
