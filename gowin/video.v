// One video module. The build switch is VIDEO_ON / VIDEO_SQUARE,
// written by the HyperRAM Tcl from VIDEO_MODE. Flash is timing and
// the TMDS pins. Square adds the 32×24 screen and includes flash.
// Text is a later mode of this same module; it is not elaborated.
//
// The Nano 4K has two PLLVR (DS861). HyperRAM already uses one, and
// its spare outputs are 54, 27, and 18 MHz, not a 5× pixel clock.
// The other PLLVR's dedicated pin is 35, which the schematic wires
// to HDMI TX2_P. This device has no DCC, so the video PLL takes the
// same 27 MHz port as the HyperRAM PLL (UG286: a PLL reference may
// be a routed clock, not only its own pin).
//
// The pixel clock is that 27 MHz port, and the serializer clock is
// 5× it (135 MHz, VCO 540, inside the C6/I5 320–960 window). A
// first bitstream used CLKDIV /5 for a 25.2 MHz pixel clock. That
// divider is not a 50% clock, and the capture card showed snow
// rather than a picture. 800×525 at 27 MHz is 64.3 Hz.
//
// Black and white are fixed 10-bit words, not an encoder. Each has
// five ones, so repeating it holds the disparity at zero. They are
// the cnt=0 encodings of bytes 0x10 and 0xEF, the darkest and
// brightest bytes with that property. 0x00 and 0xFF have none.
// Channel 0 carries VSYNC/HSYNC during blanking. The other two
// channels carry control 00. The clock channel is five ones then
// five zeros, LSB first.

module video (
  input  clk27,
  input  led,
`ifdef VIDEO_SQUARE
  input  screen_we,
  input  screen_bit,
  input  armed,
`ifndef VIDEO_SIM
  input  clk_cpu,
`endif
`endif
`ifdef VIDEO_SIM
  input  pix_sim,
  output [9:0] word0,
  output [9:0] word1,
  output [9:0] word2,
  output de_q,
  output hs_q,
  output vs_q,
  output [9:0] x_q,
  output [9:0] y_q,
`endif
  output tmds_clk_p,
  output tmds_clk_n,
  output [2:0] tmds_d_p,
  output [2:0] tmds_d_n
);

  localparam [9:0] BLACK = 10'b0111110000;
  localparam [9:0] WHITE = 10'b1011110000;
  localparam [9:0] CTRL00 = 10'b1101010100;
  localparam [9:0] CTRL01 = 10'b0010101011;
  localparam [9:0] CTRL10 = 10'b0101010100;
  localparam [9:0] CTRL11 = 10'b1010101011;

`ifdef VIDEO_SIM
  wire pix = pix_sim;
  wire pll_lock = 1'b1;
`else
  wire serial_clk;
  wire pll_lock;
  wire pix = clk27;

  // 27 * 5 = 135. ODIV 4 puts the VCO at 540 MHz.
  wire clkoutp_unused;
  wire clkoutd_unused;
  wire clkoutd3_unused;
  wire pll_vcc = 1'b1;
  wire pll_gnd = 1'b0;

  PLLVR u_pll (
    .CLKOUT   (serial_clk),
    .LOCK     (pll_lock),
    .CLKOUTP  (clkoutp_unused),
    .CLKOUTD  (clkoutd_unused),
    .CLKOUTD3 (clkoutd3_unused),
    .RESET    (pll_gnd),
    .RESET_P  (pll_gnd),
    .CLKIN    (clk27),
    .CLKFB    (pll_gnd),
    .FBDSEL   ({pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .IDSEL    ({pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .ODSEL    ({pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .PSDA     ({pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .DUTYDA   ({pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .FDLY     ({pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .VREN     (pll_vcc)
  );
  defparam u_pll.FCLKIN = "27";
  defparam u_pll.DYN_IDIV_SEL = "false";
  defparam u_pll.IDIV_SEL = 0;
  defparam u_pll.DYN_FBDIV_SEL = "false";
  defparam u_pll.FBDIV_SEL = 4;
  defparam u_pll.DYN_ODIV_SEL = "false";
  defparam u_pll.ODIV_SEL = 4;
  defparam u_pll.PSDA_SEL = "0000";
  defparam u_pll.DYN_DA_EN = "true";
  defparam u_pll.DUTYDA_SEL = "1000";
  defparam u_pll.CLKOUT_FT_DIR = 1'b1;
  defparam u_pll.CLKOUTP_FT_DIR = 1'b1;
  defparam u_pll.CLKOUT_DLY_STEP = 0;
  defparam u_pll.CLKOUTP_DLY_STEP = 0;
  defparam u_pll.CLKFB_SEL = "internal";
  defparam u_pll.CLKOUT_BYPASS = "false";
  defparam u_pll.CLKOUTP_BYPASS = "false";
  defparam u_pll.CLKOUTD_BYPASS = "false";
  defparam u_pll.DYN_SDIV_SEL = 2;
  defparam u_pll.CLKOUTD_SRC = "CLKOUT";
  defparam u_pll.CLKOUTD3_SRC = "CLKOUT";
  defparam u_pll.DEVICE = "GW1NSR-4C";
`endif

  // 640×480, 800×525. Sync pulses are negative: the control bit is 0
  // during the pulse and 1 otherwise. The frame rate follows the
  // pixel clock: 64.3 Hz at 27 MHz.
  reg [9:0] hx = 10'd0;
  reg [9:0] vy = 10'd0;
  wire hs = (hx >= 10'd96);
  wire vs = (vy >= 10'd2);
  wire active_x = (hx >= 10'd144) && (hx < 10'd784);
  wire active_y = (vy >= 10'd35) && (vy < 10'd515);
  wire de = active_x && active_y;

  reg led_s1 = 1'b0;
  reg led_s2 = 1'b0;
  reg [9:0] word0_r = BLACK;
  reg [9:0] word1_r = CTRL00;
  reg [9:0] word2_r = CTRL00;
  reg de_r = 1'b0;
  reg hs_r = 1'b0;
  reg vs_r = 1'b0;
  reg [9:0] x_r = 10'd0;
  reg [9:0] y_r = 10'd0;

`ifdef VIDEO_SQUARE
  // 32×24 blocks, 20×20 pixels. Blink5 writes only block (15, 11),
  // which is 11*32+15. The other 767 bits stay 0, so the rest of
  // the screen stays black. The read is one pixel behind the scan
  // counters; bx_d/by_d are the same pixel the bit belongs to.
  localparam [9:0] BLOCK = 10'd367;
  reg [4:0] bx = 5'd0;
  reg [4:0] by = 5'd0;
  reg [4:0] sx = 5'd0;
  reg [4:0] sy = 5'd0;
  reg [4:0] bx_d = 5'd0;
  reg [4:0] by_d = 5'd0;
  reg armed_s1 = 1'b0;
  reg armed_s2 = 1'b0;
  wire [9:0] rad = {by, bx};
  wire rbit;
`ifdef VIDEO_SIM
  reg mem [0:767];
  integer mi;
  initial for (mi = 0; mi < 768; mi = mi + 1) mem[mi] = 1'b0;
  reg rbit_r = 1'b0;
  always @(posedge pix) begin
    if (screen_we)
      mem[BLOCK] <= screen_bit;
    rbit_r <= mem[rad];
  end
  assign rbit = rbit_r;
`else
  wire [31:0] ram_do;
  SDPB u_screen (
    .DO(ram_do),
    .DI({31'b0, screen_bit}),
    .BLKSELA(3'b000),
    .BLKSELB(3'b000),
    .ADA({4'b0, BLOCK}),
    .ADB({4'b0, rad}),
    .CLKA(clk_cpu),
    .CLKB(pix),
    .CEA(screen_we),
    .CEB(1'b1),
    .OCE(1'b1),
    .RESETA(1'b0),
    .RESETB(1'b0)
  );
  defparam u_screen.READ_MODE = 1'b0;
  defparam u_screen.BIT_WIDTH_0 = 1;
  defparam u_screen.BIT_WIDTH_1 = 1;
  defparam u_screen.BLK_SEL_0 = 3'b000;
  defparam u_screen.BLK_SEL_1 = 3'b000;
  defparam u_screen.RESET_MODE = "SYNC";
  assign rbit = ram_do[0];
`endif
  wire [9:0] ctrl0 =
      ({vs_r, hs_r} == 2'b00) ? CTRL00 :
      ({vs_r, hs_r} == 2'b01) ? CTRL01 :
      ({vs_r, hs_r} == 2'b10) ? CTRL10 : CTRL11;
  // armed gates the block the way it gates the LED. The store itself
  // is not thrown away: the bit is remembered, and it stays dark
  // until the arm word.
  wire square_on = de_r && rbit && armed_s2 && (bx_d == 5'd15) && (by_d == 5'd11);
  wire [9:0] word0_o = !de_r ? ctrl0 : (square_on ? WHITE : BLACK);
  wire [9:0] word1_o = !de_r ? CTRL00 : (square_on ? WHITE : BLACK);
  wire [9:0] word2_o = word1_o;
`endif

  // led is the CPU's ledState && armed, on the CPU clock.
  always @(posedge pix) begin
    led_s1 <= led;
    led_s2 <= led_s1;
    x_r <= hx;
    y_r <= vy;
    de_r <= de;
    hs_r <= hs;
    vs_r <= vs;
`ifdef VIDEO_SQUARE
    armed_s1 <= armed;
    armed_s2 <= armed_s1;
    bx_d <= bx;
    by_d <= by;
    if ((hx == 10'd0) && (vy == 10'd0)) begin
      bx <= 5'd0;
      by <= 5'd0;
      sx <= 5'd0;
      sy <= 5'd0;
    end else if (de) begin
      if (hx == 10'd783) begin
        bx <= 5'd0;
        sx <= 5'd0;
        if (sy == 5'd19) begin
          sy <= 5'd0;
          by <= by + 5'd1;
        end else begin
          sy <= sy + 5'd1;
        end
      end else if (sx == 5'd19) begin
        sx <= 5'd0;
        bx <= bx + 5'd1;
      end else begin
        sx <= sx + 5'd1;
      end
    end
`else
    if (!de) begin
      case ({vs, hs})
        2'b00: word0_r <= CTRL00;
        2'b01: word0_r <= CTRL01;
        2'b10: word0_r <= CTRL10;
        default: word0_r <= CTRL11;
      endcase
      word1_r <= CTRL00;
      word2_r <= CTRL00;
    end else if (led_s2) begin
      word0_r <= WHITE;
      word1_r <= WHITE;
      word2_r <= WHITE;
    end else begin
      word0_r <= BLACK;
      word1_r <= BLACK;
      word2_r <= BLACK;
    end
`endif
    if (hx == 10'd799) begin
      hx <= 10'd0;
      if (vy == 10'd524)
        vy <= 10'd0;
      else
        vy <= vy + 10'd1;
    end else begin
      hx <= hx + 10'd1;
    end
  end

`ifdef VIDEO_SIM
`ifdef VIDEO_SQUARE
  assign word0 = word0_o;
  assign word1 = word1_o;
  assign word2 = word2_o;
`else
  assign word0 = word0_r;
  assign word1 = word1_r;
  assign word2 = word2_r;
`endif
  assign de_q = de_r;
  assign hs_q = hs_r;
  assign vs_q = vs_r;
  assign x_q = x_r;
  assign y_q = y_r;
  assign tmds_clk_p = 1'b0;
  assign tmds_clk_n = 1'b0;
  assign tmds_d_p = 3'b000;
  assign tmds_d_n = 3'b000;
`else
  wire [2:0] ser;
  wire ser_clk;

  OSER10 u_clk (
    .Q(ser_clk),
    .D0(1'b1), .D1(1'b1), .D2(1'b1), .D3(1'b1), .D4(1'b1),
    .D5(1'b0), .D6(1'b0), .D7(1'b0), .D8(1'b0), .D9(1'b0),
    .PCLK(pix),
    .FCLK(serial_clk),
    .RESET(~pll_lock)
  );
  defparam u_clk.GSREN = "false";
  defparam u_clk.LSREN = "false";

  TLVDS_OBUF u_clk_buf (
    .I  (ser_clk),
    .O  (tmds_clk_p),
    .OB (tmds_clk_n)
  );

  wire [9:0] q_ch [0:2];
`ifdef VIDEO_SQUARE
  assign q_ch[0] = word0_o;
  assign q_ch[1] = word1_o;
  assign q_ch[2] = word2_o;
`else
  assign q_ch[0] = word0_r;
  assign q_ch[1] = word1_r;
  assign q_ch[2] = word2_r;
`endif

  genvar gi;
  generate
    for (gi = 0; gi < 3; gi = gi + 1) begin : g_ch
      OSER10 u_ser (
        .Q(ser[gi]),
        .D0(q_ch[gi][0]), .D1(q_ch[gi][1]), .D2(q_ch[gi][2]),
        .D3(q_ch[gi][3]), .D4(q_ch[gi][4]), .D5(q_ch[gi][5]),
        .D6(q_ch[gi][6]), .D7(q_ch[gi][7]), .D8(q_ch[gi][8]),
        .D9(q_ch[gi][9]),
        .PCLK(pix),
        .FCLK(serial_clk),
        .RESET(~pll_lock)
      );
      defparam u_ser.GSREN = "false";
      defparam u_ser.LSREN = "false";

      TLVDS_OBUF u_buf (
        .I  (ser[gi]),
        .O  (tmds_d_p[gi]),
        .OB (tmds_d_n[gi])
      );
    end
  endgenerate
`endif

endmodule
