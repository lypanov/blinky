// One video module. The build switch is VIDEO_ON / VIDEO_SQUARE /
// VIDEO_TEXT / VIDEO_DOCK, written into video_mode.vh from VIDEO_MODE.
// Flash is timing and the TMDS pins. Square adds the 32×24 screen and
// includes flash. Text adds the 40×15 character window and includes
// square. The 4K build stops at square. VIDEO_DOCK is the Primer 20K:
// an rPLL instead of the Nano's PLLVR.
// The pixel clock is still the 27 MHz port, and the serializer is 5×.

`ifndef VIDEO_SIM
`include "video_mode.vh"
`endif
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
  // Forces every active pixel black. The square bit and the digits
  // keep updating, so clearing this shows the phase already stored.
  input  blank,
`ifdef VIDEO_SQUARE
  input  screen_we,
  input  screen_bit,
  input  armed,
`ifndef VIDEO_SIM
  input  clk_cpu,
`endif
`ifdef VIDEO_TEXT
  // -76 is the blink count. This block writes four decimal digits.
  input  text_we,
  input  [23:0] text_word,
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

  // 27 * 5 = 135. On the Nano, ODIV 4 puts the PLLVR VCO at 540.
  // On the Dock the rPLL's CLKOUT is fin*(FBDIV+1)/(IDIV+1), the same
  // formula as the DDR3 PLL, so FBDIV 4 is 135 MHz and ODIV 4 keeps
  // the VCO at 540.
  wire clkoutp_unused;
  wire clkoutd_unused;
  wire clkoutd3_unused;
  wire pll_vcc = 1'b1;
  wire pll_gnd = 1'b0;

`ifdef VIDEO_DOCK
  rPLL u_pll (
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
    .FDLY     ({pll_gnd, pll_gnd, pll_gnd, pll_gnd})
  );
  defparam u_pll.FCLKIN = "27";
  defparam u_pll.DYN_IDIV_SEL = "false";
  defparam u_pll.IDIV_SEL = 0;
  defparam u_pll.DYN_FBDIV_SEL = "false";
  defparam u_pll.FBDIV_SEL = 4;
  defparam u_pll.DYN_ODIV_SEL = "false";
  defparam u_pll.ODIV_SEL = 4;
  defparam u_pll.PSDA_SEL = "0000";
  defparam u_pll.DYN_DA_EN = "false";
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
  defparam u_pll.DEVICE = "GW2A-18C";
`else
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
  reg blank_s1 = 1'b0;
  reg blank_s2 = 1'b0;
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
`ifdef VIDEO_TEXT
  // 40×15 characters, 8×8, origin (160, 48) of the active picture.
  // Columns 18..21 of row 0 are Blink5's four digits. The rest of
  // the window stays the blank code. A glyph of 0 does not cover
  // the square; the two do not overlap.
  localparam [9:0] TEXT_X = 10'd160;
  localparam [9:0] TEXT_Y = 10'd48;
  localparam [9:0] TEXT_W = 10'd320;
  localparam [9:0] TEXT_H = 10'd120;
  wire [9:0] ax = hx - 10'd144;
  wire [9:0] ay = vy - 10'd35;
  wire in_text = de && (ax >= TEXT_X) && (ax < TEXT_X + TEXT_W)
      && (ay >= TEXT_Y) && (ay < TEXT_Y + TEXT_H);
  wire [9:0] tx = ax - TEXT_X;
  wire [9:0] ty = ay - TEXT_Y;
  wire [5:0] tcol = tx[8:3];
  wire [3:0] trow = ty[6:3];
  wire [9:0] taddr = in_text
      ? ({1'b0, trow, 5'b0} + {3'b0, trow, 3'b0} + {4'b0, tcol})
      : 10'd0;
  // Columns 18..21 of row 0 are the four digits. One bit per
  // clock: fourteen clocks a digit, four digits, units first.
  reg dig_run = 1'b0;
  reg [1:0] dig_phase = 2'd0;
  reg [3:0] dig_bi = 4'd0;
  reg [13:0] dig_src = 14'd0;
  reg [13:0] dig_quot = 14'd0;
  reg [4:0] dig_acc = 5'd0;
  wire dig_msb = dig_src[13];
  wire [4:0] dig_acc_n = {dig_acc[3:0], dig_msb};
  wire dig_sub = dig_acc_n >= 5'd10;
  wire [4:0] dig_acc_d = dig_sub ? (dig_acc_n - 5'd10) : dig_acc_n;
  wire dig_last = dig_bi == 4'd0;
  wire dig_we = dig_run && !text_we && dig_last;
  wire [5:0] dig_col = 6'd21 - {4'b0, dig_phase};
  wire [9:0] dig_addr = {4'b0, dig_col};
  wire [7:0] dig_ascii = {4'b0011, dig_acc_d[3:0]};
  wire [15:0] dig_in = text_word[15:0];
  wire [13:0] dig_mod = dig_in >= 16'd10000 ? dig_in[13:0] - 14'd10000 : dig_in[13:0];
  reg in_text_d = 1'b0;
  reg [2:0] subx_d = 3'd0;
  reg [2:0] suby_d = 3'd0;
`ifdef VIDEO_SIM
  reg [7:0] tmem [0:599];
  integer ti;
  initial for (ti = 0; ti < 600; ti = ti + 1) tmem[ti] = 8'h00;
  reg [7:0] char_q = 8'h00;
  always @(posedge pix) begin
    if (text_we) begin
      dig_src <= dig_mod;
      dig_quot <= 14'd0;
      dig_acc <= 5'd0;
      dig_bi <= 4'd13;
      dig_phase <= 2'd0;
      dig_run <= 1'b1;
    end else if (dig_run) begin
      if (dig_we)
        tmem[dig_addr] <= dig_ascii;
      if (dig_last) begin
        dig_src <= {dig_quot[12:0], dig_sub};
        dig_quot <= 14'd0;
        dig_acc <= 5'd0;
        dig_bi <= 4'd13;
        if (dig_phase == 2'd3)
          dig_run <= 1'b0;
        else
          dig_phase <= dig_phase + 2'd1;
      end else begin
        dig_src <= {dig_src[12:0], 1'b0};
        dig_quot <= {dig_quot[12:0], dig_sub};
        dig_acc <= dig_acc_d;
        dig_bi <= dig_bi - 4'd1;
      end
    end
    char_q <= tmem[taddr];
  end
`else
  // A second SDPB, free or pinned beside the square bitmap, held
  // DDR3 training. The four digits are registers. The count is the
  // number of on-stores at -80, so the CPU and Blink5 stay the
  // square image that trains.
  reg [15:0] blinks = 16'd0;
  reg [7:0] d0 = 8'h30;
  reg [7:0] d1 = 8'h30;
  reg [7:0] d2 = 8'h30;
  reg [7:0] d3 = 8'h30;
  wire [15:0] nxt = blinks + 16'd1;
  wire [13:0] nxt_mod = nxt >= 16'd10000 ? nxt[13:0] - 14'd10000 : nxt[13:0];
  always @(posedge clk_cpu) begin
    if (screen_we && screen_bit) begin
      blinks <= nxt;
      dig_src <= nxt_mod;
      dig_quot <= 14'd0;
      dig_acc <= 5'd0;
      dig_bi <= 4'd13;
      dig_phase <= 2'd0;
      dig_run <= 1'b1;
    end else if (dig_run) begin
      if (dig_last) begin
        dig_src <= {dig_quot[12:0], dig_sub};
        dig_quot <= 14'd0;
        dig_acc <= 5'd0;
        dig_bi <= 4'd13;
        if (dig_phase == 2'd3)
          dig_run <= 1'b0;
        else
          dig_phase <= dig_phase + 2'd1;
      end else begin
        dig_src <= {dig_src[12:0], 1'b0};
        dig_quot <= {dig_quot[12:0], dig_sub};
        dig_acc <= dig_acc_d;
        dig_bi <= dig_bi - 4'd1;
      end
      if (dig_we) begin
        case (dig_phase)
          2'd0: d3 <= dig_ascii;
          2'd1: d2 <= dig_ascii;
          2'd2: d1 <= dig_ascii;
          default: d0 <= dig_ascii;
        endcase
      end
    end
  end
  reg [7:0] char_q = 8'h30;
  always @(posedge pix) begin
    if (taddr == 10'd18) char_q <= d0;
    else if (taddr == 10'd19) char_q <= d1;
    else if (taddr == 10'd20) char_q <= d2;
    else if (taddr == 10'd21) char_q <= d3;
    else char_q <= 8'h00;
  end
`endif
  // FONT8 BEGIN
  function [7:0] font8;
    input [7:0] ch;
    input [2:0] row;
    begin
      case ({ch, row})
        11'h180: font8 = 8'h7E;
        11'h181: font8 = 8'h81;
        11'h182: font8 = 8'h81;
        11'h183: font8 = 8'h81;
        11'h184: font8 = 8'h81;
        11'h185: font8 = 8'h81;
        11'h186: font8 = 8'h7E;
        11'h187: font8 = 8'h00;
        11'h188: font8 = 8'h18;
        11'h189: font8 = 8'h38;
        11'h18A: font8 = 8'h18;
        11'h18B: font8 = 8'h18;
        11'h18C: font8 = 8'h18;
        11'h18D: font8 = 8'h18;
        11'h18E: font8 = 8'h7E;
        11'h18F: font8 = 8'h00;
        11'h190: font8 = 8'h7E;
        11'h191: font8 = 8'h02;
        11'h192: font8 = 8'h02;
        11'h193: font8 = 8'h7E;
        11'h194: font8 = 8'h80;
        11'h195: font8 = 8'h80;
        11'h196: font8 = 8'h7E;
        11'h197: font8 = 8'h00;
        11'h198: font8 = 8'h7E;
        11'h199: font8 = 8'h02;
        11'h19A: font8 = 8'h02;
        11'h19B: font8 = 8'h7E;
        11'h19C: font8 = 8'h02;
        11'h19D: font8 = 8'h02;
        11'h19E: font8 = 8'h7E;
        11'h19F: font8 = 8'h00;
        11'h1A0: font8 = 8'h81;
        11'h1A1: font8 = 8'h81;
        11'h1A2: font8 = 8'h81;
        11'h1A3: font8 = 8'h7E;
        11'h1A4: font8 = 8'h02;
        11'h1A5: font8 = 8'h02;
        11'h1A6: font8 = 8'h02;
        11'h1A7: font8 = 8'h00;
        11'h1A8: font8 = 8'h7E;
        11'h1A9: font8 = 8'h80;
        11'h1AA: font8 = 8'h80;
        11'h1AB: font8 = 8'h7E;
        11'h1AC: font8 = 8'h02;
        11'h1AD: font8 = 8'h02;
        11'h1AE: font8 = 8'h7E;
        11'h1AF: font8 = 8'h00;
        11'h1B0: font8 = 8'h7E;
        11'h1B1: font8 = 8'h80;
        11'h1B2: font8 = 8'h80;
        11'h1B3: font8 = 8'h7E;
        11'h1B4: font8 = 8'h81;
        11'h1B5: font8 = 8'h81;
        11'h1B6: font8 = 8'h7E;
        11'h1B7: font8 = 8'h00;
        11'h1B8: font8 = 8'h7E;
        11'h1B9: font8 = 8'h02;
        11'h1BA: font8 = 8'h02;
        11'h1BB: font8 = 8'h04;
        11'h1BC: font8 = 8'h08;
        11'h1BD: font8 = 8'h10;
        11'h1BE: font8 = 8'h10;
        11'h1BF: font8 = 8'h00;
        11'h1C0: font8 = 8'h7E;
        11'h1C1: font8 = 8'h81;
        11'h1C2: font8 = 8'h81;
        11'h1C3: font8 = 8'h7E;
        11'h1C4: font8 = 8'h81;
        11'h1C5: font8 = 8'h81;
        11'h1C6: font8 = 8'h7E;
        11'h1C7: font8 = 8'h00;
        11'h1C8: font8 = 8'h7E;
        11'h1C9: font8 = 8'h81;
        11'h1CA: font8 = 8'h81;
        11'h1CB: font8 = 8'h7E;
        11'h1CC: font8 = 8'h02;
        11'h1CD: font8 = 8'h02;
        11'h1CE: font8 = 8'h7E;
        11'h1CF: font8 = 8'h00;
        default: font8 = 8'h00;
      endcase
    end
  endfunction
  // FONT8 END
  wire [7:0] grow = font8(char_q, suby_d);
  wire gbit = grow[3'd7 - subx_d];
  wire text_on = de_r && in_text_d && armed_s2 && gbit;
`else
  wire text_on = 1'b0;
`endif
  wire [9:0] ctrl0 =
      ({vs_r, hs_r} == 2'b00) ? CTRL00 :
      ({vs_r, hs_r} == 2'b01) ? CTRL01 :
      ({vs_r, hs_r} == 2'b10) ? CTRL10 : CTRL11;
  // armed gates the block the way it gates the LED. The store itself
  // is not thrown away: the bit is remembered, and it stays dark
  // until the arm word.
  wire square_on = de_r && rbit && armed_s2 && (bx_d == 5'd15) && (by_d == 5'd11);
  wire lit = (square_on || text_on) && !blank_s2;
  wire [9:0] word0_o = !de_r ? ctrl0 : (lit ? WHITE : BLACK);
  wire [9:0] word1_o = !de_r ? CTRL00 : (lit ? WHITE : BLACK);
  wire [9:0] word2_o = word1_o;
`endif

  // led is the CPU's ledState && armed, on the CPU clock.
  always @(posedge pix) begin
    led_s1 <= led;
    led_s2 <= led_s1;
    blank_s1 <= blank;
    blank_s2 <= blank_s1;
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
`ifdef VIDEO_TEXT
    in_text_d <= in_text;
    subx_d <= tx[2:0];
    suby_d <= ty[2:0];
`endif
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
    end else if (led_s2 && !blank_s2) begin
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

`ifdef VIDEO_DOCK
  // The Dock bank is 3.3 V. LVCMOS33D on the positive port makes the
  // pair, the same IO type NESTang placed on these balls. TLVDS_OBUF
  // rejects that type.
  assign tmds_clk_p = ser_clk;
  assign tmds_clk_n = 1'b0;
`else
  TLVDS_OBUF u_clk_buf (
    .I  (ser_clk),
    .O  (tmds_clk_p),
    .OB (tmds_clk_n)
  );
`endif

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

`ifdef VIDEO_DOCK
      assign tmds_d_p[gi] = ser[gi];
      assign tmds_d_n[gi] = 1'b0;
`else
      TLVDS_OBUF u_buf (
        .I  (ser[gi]),
        .O  (tmds_d_p[gi]),
        .OB (tmds_d_n[gi])
      );
`endif
    end
  endgenerate
`endif

endmodule
