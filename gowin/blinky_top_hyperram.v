`include "video_mode.vh"

// Tang Nano 4K wrapper for the HyperRAM data port.
//
// The bridge runs on the IP's clk_out (memory clock / 2, 27 MHz).
// The Modules CPU runs on clk_out/2 (13.5 MHz): the fetch address and
// the register write leave the instruction pROM and miss 27 MHz.
// The HyperRAM IP itself is clocked by the 27 MHz crystal (clk) and by
// the 54 MHz PLL (memory_clk). O_hpram_* / IO_hpram_* are the embedded
// W956 pins. They must be top-level ports with these names and they must
// not appear in the CST. Fetch stays in the CPU's block RAM.

module blinky_top (
  input  clock,
  input  reset,
  output io_led,
  input  io_uart_rx,
  output io_uart_tx,
  // S1 / KEY1, package pin 14, active-low. S2 stays the reset input.
  input  io_btn_n,
  output [0:0] O_hpram_ck,
  output [0:0] O_hpram_ck_n,
  (* syn_tristate = 1 *) inout [7:0] IO_hpram_dq,
  (* syn_tristate = 1 *) inout [0:0] IO_hpram_rwds,
  output [0:0] O_hpram_cs_n,
  output [0:0] O_hpram_reset_n,
  output spi_cs_n,
  output spi_clk,
  output spi_mosi,
  input  spi_miso,
  output spi_wp,
  output spi_hold
`ifdef VIDEO_ON
  ,
  output tmds_clk_p,
  output tmds_clk_n,
  output [2:0] tmds_d_p,
  output [2:0] tmds_d_n
`endif
);

  wire memory_clk;
  wire pll_lock;
  wire clk_out;
  wire [15:0] unused_deadbeef;
  wire [2:0]  unused_addr;

  // syn_keep keeps the HyperRAM user ports. Without it, synthesis
  // pulls cmd_en, wr_data, data_mask, and addr into the encrypted PHY,
  // and the netlist no longer has those pins. The proofs that blinked
  // drove the PHY through these ports.
  (* syn_keep = 1 *) wire        hr_cmd;
  (* syn_keep = 1 *) wire        hr_cmd_en;
  (* syn_keep = 1 *) wire [21:0] hr_addr;
  (* syn_keep = 1 *) wire [31:0] hr_wr_data;
  (* syn_keep = 1 *) wire [3:0]  hr_data_mask;
  (* syn_keep = 1 *) wire [31:0] hr_rd_data;
  (* syn_keep = 1 *) wire        hr_rd_data_valid;
  (* syn_keep = 1 *) wire        hr_init_calib;

  hpram_pllvr u_pll (
    .clkout (memory_clk),
    .lock   (pll_lock),
    .clkin  (clock)
  );

  // clk_out is produced by the IP from memory_clk, including while the
  // IP is held in reset, so the power-on counter can run. The IP reset
  // follows PLL lock and the button only. The CPU stays reset a little
  // longer, then stalls on its first data access until init_calib.
  reg [7:0] por = 8'hff;
  always @(posedge clk_out or negedge pll_lock) begin
    if (!pll_lock)
      por <= 8'hff;
    else if (por != 8'h00)
      por <= por - 8'h01;
  end
  wire cpu_reset = (por != 8'h00) | reset;
  wire hr_rst_n = pll_lock & ~reset;
  wire cpu_clk;
  wire screen_we;
  wire screen_bit;
  wire [31:0] bmp_data;
  wire [12:0] bmp_word;
  wire status_we;
  wire [8:0] status_word;
  wire cpu_armed;
  wire cpu_led;
  wire pressed;

  // Runs as soon as the PLL locks, including while the CPU is still in
  // the power-on reset. DIV_MODE 2 is edge-aligned with clk_out.
  GowinClkDiv2 u_cpu_div (
    .HCLKIN (clk_out),
    .RESETN (pll_lock),
    .CALIB  (1'b0),
    .CLKOUT (cpu_clk)
  );

  (* syn_hier = "hard" *) CPUMinimalWrapper u_cpu (
    .clock             (clk_out),
    .io_cpu_clock      (cpu_clk),
    .reset             (cpu_reset),
    .io_led            (cpu_led),
    .io_deadbeef       (unused_deadbeef),
    .io_addr           (unused_addr),
    .io_uart_rx        (1'b1),
    .io_uart_tx        (io_uart_tx),
    .io_hr_cmd         (hr_cmd),
    .io_hr_cmd_en      (hr_cmd_en),
    .io_hr_addr        (hr_addr),
    .io_hr_wr_data     (hr_wr_data),
    .io_hr_data_mask   (hr_data_mask),
    .io_hr_rd_data     (hr_rd_data),
    .io_hr_rd_data_valid (hr_rd_data_valid),
    .io_hr_init_calib  (hr_init_calib),
    .io_spi_cs_n       (spi_cs_n),
    .io_spi_clk        (spi_clk),
    .io_spi_mosi       (spi_mosi),
    .io_spi_miso       (spi_miso),
    .io_screen_we      (screen_we),
    .io_screen_bit     (screen_bit),
    .io_bmp_data       (bmp_data),
    .io_bmp_word       (bmp_word),
    .io_armed          (cpu_armed),
    .io_status_we      (status_we),
    .io_status_word    (status_word),
    .io_btnPressed     (pressed)
  );

  // WP# and HOLD# stay deasserted. They are not part of the CPU.
  assign spi_wp = 1'b1;
  assign spi_hold = 1'b1;

  // cpu_clk is 13.5 MHz. 13500000/115200 = 117.1875.
  // The pin is the CPU register. S1 and a press byte are the switch
  // bit Blink polls. UART bytes before the arm word are ignored.
  assign io_led = cpu_led;
  wire gate_rx = cpu_armed ? io_uart_rx : 1'b1;
  button_gate #(.CLKS_PER_BIT(117)) u_gate (
    .clk     (cpu_clk),
    .resetn  (~cpu_reset),
    .btn_n   (io_btn_n),
    .uart_rx (gate_rx),
    .pressed (pressed)
  );

  (* syn_hier = "hard" *) HyperRAM_Memory_Interface_Top u_hpram (
    .clk             (clock),
    .memory_clk      (memory_clk),
    .pll_lock        (pll_lock),
    .rst_n           (hr_rst_n),
    .O_hpram_ck      (O_hpram_ck),
    .O_hpram_ck_n    (O_hpram_ck_n),
    .IO_hpram_dq     (IO_hpram_dq),
    .IO_hpram_rwds   (IO_hpram_rwds),
    .O_hpram_cs_n    (O_hpram_cs_n),
    .O_hpram_reset_n (O_hpram_reset_n),
    .wr_data         (hr_wr_data),
    .rd_data         (hr_rd_data),
    .rd_data_valid   (hr_rd_data_valid),
    .addr            (hr_addr),
    .cmd             (hr_cmd),
    .cmd_en          (hr_cmd_en),
    .init_calib      (hr_init_calib),
    .clk_out         (clk_out),
    .data_mask       (hr_data_mask)
  );

`ifdef VIDEO_ON
  // io_led is already ledState && armed. Flash paints the whole
  // screen from it. Square ignores it and paints one stored block;
  // cpu_armed keeps that block dark until the arm word.
  video u_video (
    .clk27      (clock),
    .led        (io_led),
    .blank      (1'b0),
`ifdef VIDEO_SQUARE
    .screen_we  (screen_we),
    .screen_bit (screen_bit),
    .bmp_data   (bmp_data),
    .bmp_word   (bmp_word),
    .armed      (cpu_armed),
    .status_we  (status_we),
    .status_in  (status_word),
    .clk_cpu    (cpu_clk),
`endif
    .tmds_clk_p (tmds_clk_p),
    .tmds_clk_n (tmds_clk_n),
    .tmds_d_p   (tmds_d_p),
    .tmds_d_n   (tmds_d_n)
  );
`endif

endmodule
