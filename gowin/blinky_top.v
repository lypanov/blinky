// Board wrapper for Tang Nano 4K.
// Pin 45 is LPLL_T_in: feed it through PLLVR so the 27 MHz clock is global.
// a68a501: reset pin 15 is PULL_DOWN and Chisel reset is active-high, so the
// unpressed KEY (low) leaves the CPU running. Do not invert.
// io_deadbeef / io_addr stay internal so PNR cannot park them on MSPI/flash.

module blinky_top (
  input  clock,
  input  reset,
  output io_led,
  input  io_uart_rx,
  output io_uart_tx,
  input  io_btn_n
);

  wire clk_sys;
  wire [15:0] unused_deadbeef;
  wire [2:0]  unused_addr;

  Gowin_PLLVR u_pll (
    .clkout (clk_sys),
    .clkin  (clock)
  );

  // Short power-on reset, then follow pin 15 (pull-down → 0 → run).
  reg [7:0] por = 8'hff;
  always @(posedge clk_sys) begin
    if (por != 8'h00)
      por <= por - 8'h01;
  end
  wire cpu_reset = (por != 8'h00) | reset;

  CPUMinimalWrapper u_cpu (
    .clock       (clk_sys),
    .reset       (cpu_reset),
    .io_led      (io_led),
    .io_deadbeef (unused_deadbeef),
    .io_addr     (unused_addr),
    .io_uart_rx  (io_uart_rx),
    .io_uart_tx  (io_uart_tx),
    .io_btn_n    (io_btn_n)
  );

endmodule
