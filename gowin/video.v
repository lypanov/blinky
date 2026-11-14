// One video module. The build switch is VIDEO_ON / VIDEO_SQUARE /
// VIDEO_TEXT / VIDEO_DOCK, written into video_mode.vh from VIDEO_MODE.
// Flash is timing and the TMDS pins. Square adds the 32×24 screen and
// includes flash. Text adds the 40×15 character window and includes
// square. The 4K build stops at square. VIDEO_DOCK is the Primer 20K:
// 1024×768 timing and two rPLLs. The 4K stays at 720×480 on its PLLVR.

`ifndef VIDEO_SIM
`include "video_mode.vh"
`endif
// FRAME_CHECK is the Verilator frame tap. The screen write uses the
// CPU clock, the same way the board does. Gowin does not set
// FRAME_CHECK. The digit converter and the glyph ROM are retired.
//
// The Nano 4K has two PLLVR (DS861). HyperRAM already uses one, and
// its spare outputs are 54, 27, and 18 MHz, not a 5× pixel clock.
// The other PLLVR's dedicated pin is 35, which the schematic wires
// to HDMI TX2_P. This device has no DCC, so the video PLL takes the
// same 27 MHz port as the HyperRAM PLL (UG286: a PLL reference may
// be a routed clock, not only its own pin).
//
// The Nano pixel clock is that 27 MHz port, and the serializer is
// 5× it (135 MHz, VCO 540, inside the C6/I5 320–960 window). A
// first bitstream used CLKDIV /5 for a 25.2 MHz pixel clock. That
// divider is not a 50% clock, and the capture card showed snow
// rather than a picture. CEA 480p is 858×525 at this same 27 MHz,
// 59.94 Hz. The earlier 800×525 totals were 64.3 Hz.
//
// The Dock screen is 1024×768. CLKOUTD's divider is even only, so
// it cannot make the pixel clock as the serializer divided by 5.
// Two rPLLs keep both clocks at 50%: 27×12/5 = 64.8 MHz, then that
// clock times 5 = 324 MHz. 64.8 is 0.31% under the 65 MHz book
// clock. 1344×806 at 64.8 MHz is 59.82 Hz.
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
  // One ordinary word. bmp_word is the word index inside this board's
  // bitmap. Bit 0 of the word is the leftmost pixel of that group of 32.
  input  [31:0] bmp_data,
  input  [12:0] bmp_word,
  input  armed,
  // -84. Bits 0-7 are the status byte. Bit 8 is 0 for the status
  // blocks and 1 for today's square picture. The nine flops sit on
  // the CPU clock. The pixel clock samples them.
  input  status_we,
  input  [8:0] status_in,
`ifndef VIDEO_SIM
  input  clk_cpu,
`ifdef VIDEO_DOCK
  // The Dock shadow is read here. Both ports stay on the pixel clock.
  // A CPU-clock write port is what drags the DDR3 write off.
  input  [12:0] bmp_rd_addr,
  input         bmp_rd_req,
  output [31:0] bmp_rd_data,
  output        bmp_rd_ack,
`endif
`elsif FRAME_CHECK
  input  clk_cpu,
`endif
`ifdef VIDEO_TEXT
  // The digit converter is retired. The ports stay so the top connects.
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
`ifdef VIDEO_DOCK
  output [10:0] x_q,
`else
  output [9:0] x_q,
`endif
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
`ifdef VIDEO_DOCK
  // 50% pixel clock, then a second rPLL locked to it at 5×. The
  // serializer relationship is the same one the 27 MHz port uses.
  wire pix_clk;
  wire pix_lock;
  wire ser_lock;
  assign pll_lock = pix_lock & ser_lock;
  wire pix = pix_clk;
`else
  wire pix = clk27;
`endif

  // On the Nano, ODIV 8 puts the PLLVR VCO at 1080 MHz, inside the
  // tool's 600–1200 window, and CLKOUT stays 135 MHz:
  // 27*(4+1)*8/(0+1) = 1080, then divided by ODIV. ODIV 4 was a
  // 540 MHz VCO, under that window. On the Dock the pixel rPLL is
  // 27*(11+1)/(4+1) = 64.8 MHz with ODIV 16 (VCO 1036.8). The
  // serializer rPLL is 64.8*5 = 324 MHz with ODIV 2 (VCO 648).
  wire clkoutp_unused;
  wire clkoutd_unused;
  wire clkoutd3_unused;
`ifdef VIDEO_DOCK
  wire ser_p_unused;
  wire ser_d_unused;
  wire ser_d3_unused;
`endif
  wire pll_vcc = 1'b1;
  wire pll_gnd = 1'b0;

`ifdef VIDEO_DOCK
  rPLL u_pix (
    .CLKOUT   (pix_clk),
    .LOCK     (pix_lock),
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
  defparam u_pix.FCLKIN = "27";
  defparam u_pix.DYN_IDIV_SEL = "false";
  defparam u_pix.IDIV_SEL = 4;
  defparam u_pix.DYN_FBDIV_SEL = "false";
  defparam u_pix.FBDIV_SEL = 11;
  defparam u_pix.DYN_ODIV_SEL = "false";
  defparam u_pix.ODIV_SEL = 16;
  defparam u_pix.PSDA_SEL = "0000";
  defparam u_pix.DYN_DA_EN = "false";
  defparam u_pix.DUTYDA_SEL = "1000";
  defparam u_pix.CLKOUT_FT_DIR = 1'b1;
  defparam u_pix.CLKOUTP_FT_DIR = 1'b1;
  defparam u_pix.CLKOUT_DLY_STEP = 0;
  defparam u_pix.CLKOUTP_DLY_STEP = 0;
  defparam u_pix.CLKFB_SEL = "internal";
  defparam u_pix.CLKOUT_BYPASS = "false";
  defparam u_pix.CLKOUTP_BYPASS = "false";
  defparam u_pix.CLKOUTD_BYPASS = "false";
  defparam u_pix.DYN_SDIV_SEL = 2;
  defparam u_pix.CLKOUTD_SRC = "CLKOUT";
  defparam u_pix.CLKOUTD3_SRC = "CLKOUT";
  defparam u_pix.DEVICE = "GW2A-18C";

  rPLL u_ser (
    .CLKOUT   (serial_clk),
    .LOCK     (ser_lock),
    .CLKOUTP  (ser_p_unused),
    .CLKOUTD  (ser_d_unused),
    .CLKOUTD3 (ser_d3_unused),
    .RESET    (pll_gnd),
    .RESET_P  (pll_gnd),
    .CLKIN    (pix_clk),
    .CLKFB    (pll_gnd),
    .FBDSEL   ({pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .IDSEL    ({pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .ODSEL    ({pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .PSDA     ({pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .DUTYDA   ({pll_gnd, pll_gnd, pll_gnd, pll_gnd}),
    .FDLY     ({pll_gnd, pll_gnd, pll_gnd, pll_gnd})
  );
  defparam u_ser.FCLKIN = "64.8";
  defparam u_ser.DYN_IDIV_SEL = "false";
  defparam u_ser.IDIV_SEL = 0;
  defparam u_ser.DYN_FBDIV_SEL = "false";
  defparam u_ser.FBDIV_SEL = 4;
  defparam u_ser.DYN_ODIV_SEL = "false";
  defparam u_ser.ODIV_SEL = 2;
  defparam u_ser.PSDA_SEL = "0000";
  defparam u_ser.DYN_DA_EN = "false";
  defparam u_ser.DUTYDA_SEL = "1000";
  defparam u_ser.CLKOUT_FT_DIR = 1'b1;
  defparam u_ser.CLKOUTP_FT_DIR = 1'b1;
  defparam u_ser.CLKOUT_DLY_STEP = 0;
  defparam u_ser.CLKOUTP_DLY_STEP = 0;
  defparam u_ser.CLKFB_SEL = "internal";
  defparam u_ser.CLKOUT_BYPASS = "false";
  defparam u_ser.CLKOUTP_BYPASS = "false";
  defparam u_ser.CLKOUTD_BYPASS = "false";
  defparam u_ser.DYN_SDIV_SEL = 2;
  defparam u_ser.CLKOUTD_SRC = "CLKOUT";
  defparam u_ser.CLKOUTD3_SRC = "CLKOUT";
  defparam u_ser.DEVICE = "GW2A-18C";
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
  defparam u_pll.ODIV_SEL = 8;
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

  // Sync pulses are negative: the control bit is 0 during the pulse
  // and 1 otherwise. The Nano is CEA 480p, counted from the start of
  // the sync pulse: sync 62, back porch 60, active 720, front porch
  // 16 (858), and sync 6, back porch 30, active 480, front porch 9
  // (525). 858×525 at 27 MHz is 59.94 Hz. The 32×24 grid of 20×20
  // blocks is 640 wide and sits at the top left. The 80 columns past
  // it stay black. The Dock is VESA 1024×768 counted from the start
  // of the sync pulse: sync 136, back porch 160, active 1024, front
  // porch 24 (1344), and sync 6, back porch 29, active 768, front
  // porch 3 (806). The same grid is placed at the top left of that
  // picture. The rest of the screen stays black.
`ifdef VIDEO_DOCK
  reg [10:0] hx = 11'd0;
  reg [9:0] vy = 10'd0;
  wire hs = (hx >= 11'd136);
  wire vs = (vy >= 10'd6);
  wire active_x = (hx >= 11'd296) && (hx < 11'd1320);
  wire active_y = (vy >= 10'd35) && (vy < 10'd803);
`else
  reg [9:0] hx = 10'd0;
  reg [9:0] vy = 10'd0;
  wire hs = (hx >= 10'd62);
  wire vs = (vy >= 10'd6);
  wire active_x = (hx >= 10'd122) && (hx < 10'd842);
  wire active_y = (vy >= 10'd36) && (vy < 10'd516);
`endif
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
`ifdef VIDEO_DOCK
  reg [10:0] x_r = 11'd0;
`else
  reg [9:0] x_r = 10'd0;
`endif
  reg [9:0] y_r = 10'd0;

`ifdef VIDEO_SQUARE
  // The bitmap replaces the 32×24 grid. Bit 0 of a word is the left
  // pixel of that group of 32. The 4K picture is 180×120, stored on a
  // 256-bit stride so a row is eight words and each block RAM holds 64
  // whole rows: two SDPB, 32-bit write and 1-bit read. The Dock picture
  // is 512×384, sixteen words a row, twelve SDPB. Each bitmap pixel is
  // 4×4 screen pixels on the 4K and 2×2 on the Dock, so the bitmap fills
  // the active picture. The read is one pixel behind the scan.
  reg armed_s1 = 1'b0;
  reg armed_s2 = 1'b0;
  // The status register resets to 0: status mode, every block dark.
  // status_q is the pixel-clock sample. px_r/py_r are the same pixel.
  reg [8:0] status = 9'd0;
  reg [8:0] status_q = 9'd0;
`ifdef VIDEO_DOCK
  wire [10:0] px = hx - 11'd296;
  wire [9:0] py = vy - 10'd35;
  wire [8:0] bmx = px[9:1];
  wire [8:0] bmy = py[9:1];
  wire [17:0] bitad = {bmy, bmx};
`else
  wire [10:0] px = {1'b0, hx} - 11'd122;
  wire [9:0] py = vy - 10'd36;
  wire [7:0] bmx = px[9:2];
  wire [6:0] bmy = py[8:2];
  wire [17:0] bitad = {3'b0, bmy, bmx};
`endif
  wire [3:0] rram = bitad[17:14];
  wire [13:0] rbitad = bitad[13:0];
  wire [12:0] rword = bitad[17:5];
  wire [4:0] rbitn = bitad[4:0];
  // Write address. ADA[13:5] is the word in this block. ADA[3:0] are
  // the four byte enables, all set. ADA[4] stays 0.
  wire [3:0] wram = bmp_word[12:9];
  wire [13:0] wada = {bmp_word[8:0], 5'b01111};
  // Twelve write clocks on clk_cpu drag that clock off the DDR3
  // write, and the CPU leaves the boot ROM. Every picture bank stays
  // on the pixel clock. The enable is high only between two taps of a
  // LUT chain: after the latched word's +4 bit has arrived, and for
  // longer than one pixel period, before the data starts to fall.
  // The 4K writes on clk_cpu.
  wire [31:0] wr_data = bmp_data;
  wire [3:0] wram_w = wram;
  wire [13:0] wada_w = wada;
  wire fire;
`ifdef VIDEO_DOCK
`ifndef VIDEO_SIM
  wire [24:0] fire_d;
  assign fire_d[0] = screen_we;
  genvar fdi;
  generate
    for (fdi = 0; fdi < 24; fdi = fdi + 1) begin : g_fire
      KeepBit u_dly (
        .i(fire_d[fdi]),
        .o(fire_d[fdi + 1])
      );
    end
  endgenerate
  LUT2 u_fire_and (
    .I0(fire_d[4]),
    .I1(fire_d[24]),
    .F(fire)
  );
  defparam u_fire_and.INIT = 4'h2;
`else
  assign fire = screen_we;
`endif
`else
  assign fire = screen_we;
`ifndef VIDEO_SIM
  wire wr_clk = clk_cpu;
`endif
`endif
  reg [10:0] px_r = 11'd0;
  reg [9:0] py_r = 10'd0;
  reg [3:0] rram_q = 4'd0;
  wire rbit;
`ifdef VIDEO_SIM
`ifdef VIDEO_DOCK
  localparam BMP_WORDS = 6144;
`else
  localparam BMP_WORDS = 1024;
`endif
  reg [31:0] bmem [0:BMP_WORDS-1];
  integer bmi;
  initial for (bmi = 0; bmi < BMP_WORDS; bmi = bmi + 1) bmem[bmi] = 32'd0;
  reg rbit_r = 1'b0;
  wire bhit = (rword < BMP_WORDS);
  wire [12:0] rword_s = bhit ? rword : 13'd0;
`ifdef FRAME_CHECK
  // Write on the CPU clock, read on the pixel clock. Same split as
  // the SDPB on the board.
  always @(posedge clk_cpu) begin
    if (screen_we && (bmp_word < BMP_WORDS))
      bmem[bmp_word] <= bmp_data;
  end
  always @(posedge pix) begin
    rbit_r <= bhit && bmem[rword_s][rbitn];
  end
`else
  always @(posedge pix) begin
    if (screen_we && (bmp_word < BMP_WORDS))
      bmem[bmp_word] <= bmp_data;
    rbit_r <= bhit && bmem[rword_s][rbitn];
  end
`endif
  assign rbit = rbit_r;
`else
`ifdef VIDEO_DOCK
  localparam NRAM = 12;
`else
  localparam NRAM = 2;
`endif
  wire [31:0] ram_do [0:NRAM-1];
  genvar bri;
  generate
    for (bri = 0; bri < NRAM; bri = bri + 1) begin : g_bmp
`ifdef VIDEO_DOCK
      wire clka_i = pix;
`else
      wire clka_i = wr_clk;
`endif
      wire cea_i = fire && (wram_w == bri);
      SDPB u_bmp (
        .DO(ram_do[bri]),
        .DI(wr_data),
        .BLKSELA(3'b000),
        .BLKSELB(3'b000),
        .ADA(wada_w),
        .ADB(rbitad),
        .CLKA(clka_i),
        .CLKB(pix),
        .CEA(cea_i),
        .CEB(1'b1),
        .OCE(1'b1),
        .RESETA(1'b0),
        .RESETB(1'b0)
      );
      defparam u_bmp.READ_MODE = 1'b0;
      defparam u_bmp.BIT_WIDTH_0 = 32;
      defparam u_bmp.BIT_WIDTH_1 = 1;
      defparam u_bmp.BLK_SEL_0 = 3'b000;
      defparam u_bmp.BLK_SEL_1 = 3'b000;
      defparam u_bmp.RESET_MODE = "SYNC";
    end
  endgenerate
  reg rbit_mux = 1'b0;
  integer rmi;
  always @* begin
    rbit_mux = 1'b0;
    for (rmi = 0; rmi < NRAM; rmi = rmi + 1)
      if (rram_q == rmi[3:0])
        rbit_mux = ram_do[rmi][0];
  end
  assign rbit = rbit_mux;
`ifdef VIDEO_DOCK
  // Twelve more blocks, same write as the picture, 32-bit read. The
  // CPU clock and this pixel clock are unrelated. The request is
  // synchronized, the word is held, then the ack rises. The CPU drops
  // the request and waits until the ack falls.
  wire [31:0] sh_do [0:11];
  reg [12:0] addr_q = 13'd0;
  reg req_s0 = 1'b0;
  reg req_s1 = 1'b0;
  reg [31:0] data_q = 32'd0;
  reg ack = 1'b0;
  reg [1:0] sh_st = 2'd0;
  wire [13:0] sh_adb = {addr_q[8:0], 5'b00000};
  reg [31:0] sh_mux = 32'd0;
  integer shi;
  always @* begin
    sh_mux = 32'd0;
    for (shi = 0; shi < 12; shi = shi + 1)
      if (addr_q[12:9] == shi[3:0])
        sh_mux = sh_do[shi];
  end
  genvar bsi;
  generate
    for (bsi = 0; bsi < 12; bsi = bsi + 1) begin : g_shad
      SDPB u_shad (
        .DO(sh_do[bsi]),
        .DI(wr_data),
        .BLKSELA(3'b000),
        .BLKSELB(3'b000),
        .ADA(wada_w),
        .ADB(sh_adb),
        .CLKA(pix),
        .CLKB(pix),
        .CEA(fire && (wram_w == bsi)),
        .CEB(1'b1),
        .OCE(1'b1),
        .RESETA(1'b0),
        .RESETB(1'b0)
      );
      defparam u_shad.READ_MODE = 1'b0;
      defparam u_shad.BIT_WIDTH_0 = 32;
      defparam u_shad.BIT_WIDTH_1 = 32;
      defparam u_shad.BLK_SEL_0 = 3'b000;
      defparam u_shad.BLK_SEL_1 = 3'b000;
      defparam u_shad.RESET_MODE = "SYNC";
    end
  endgenerate
  // SETUP presents the address. CAP is the cycle the read data is
  // out, and that edge latches it and raises the ack.
  always @(posedge pix) begin
    req_s0 <= bmp_rd_req;
    req_s1 <= req_s0;
    case (sh_st)
      2'd0: begin
        if (req_s1) begin
          addr_q <= bmp_rd_addr;
          sh_st <= 2'd1;
        end
      end
      2'd1: sh_st <= 2'd2;
      2'd2: begin
        data_q <= sh_mux;
        ack <= 1'b1;
        sh_st <= 2'd3;
      end
      default: begin
        if (!req_s1) begin
          ack <= 1'b0;
          sh_st <= 2'd0;
        end
      end
    endcase
  end
  assign bmp_rd_data = data_q;
  assign bmp_rd_ack = ack;
`endif
`endif
  // The write is one CPU cycle, the same pulse as the square bit.
  // On the Dock the pixel clock is not an integer multiple of the
  // CPU clock, so the flops have to sit on the CPU clock. The
  // picture samples the level, which stays put after the store.
`ifdef VIDEO_SIM
`ifndef FRAME_CHECK
  always @(posedge pix) begin
    if (status_we)
      status <= status_in;
  end
`else
  always @(posedge clk_cpu) begin
    if (status_we)
      status <= status_in;
  end
`endif
`else
  always @(posedge clk_cpu) begin
    if (status_we)
      status <= status_in;
  end
`endif
  // The digit converter and the glyph ROM are retired. Blink draws
  // the count into the bitmap with the book's Texts and Fonts.
  wire text_on = 1'b0;
  wire [9:0] ctrl0 =
      ({vs_r, hs_r} == 2'b00) ? CTRL00 :
      ({vs_r, hs_r} == 2'b01) ? CTRL01 :
      ({vs_r, hs_r} == 2'b10) ? CTRL10 : CTRL11;
  // The bitmap stays dark until the arm word. Bit 8 selects it.
  // Bit 8 = 0 shows the status byte instead: eight 80×160 blocks,
  // active x 0..639 and y 160..319, bit 7 on the left. A set bit is
  // white. The blocks are not armed: they show during the boot.
  function [2:0] stat_col;
    input [9:0] x;
    begin
      if (x < 10'd80) stat_col = 3'd0;
      else if (x < 10'd160) stat_col = 3'd1;
      else if (x < 10'd240) stat_col = 3'd2;
      else if (x < 10'd320) stat_col = 3'd3;
      else if (x < 10'd400) stat_col = 3'd4;
      else if (x < 10'd480) stat_col = 3'd5;
      else if (x < 10'd560) stat_col = 3'd6;
      else stat_col = 3'd7;
    end
  endfunction
  wire in_stat = (px_r < 11'd640) && (py_r >= 10'd160) && (py_r < 10'd320);
  wire [2:0] status_col = stat_col(px_r[9:0]);
  wire status_bit = status_q[3'd7 - status_col];
  wire status_on = de_r && in_stat && !status_q[8] && status_bit;
  wire square_on = de_r && rbit && armed_s2 && status_q[8];
  wire lit = (status_on || square_on || text_on) && !blank_s2;
  // Nano 4K only: first two active rows are green. HDMI ch0 is blue,
  // ch1 green, ch2 red. Green is BLACK on ch0/ch2 and WHITE on ch1.
  // Not gated by armed or blank, so trap, stuck, and status still
  // show it. VIDEO_DOCK must not have it.
`ifndef VIDEO_DOCK
  wire marker = de_r && (py_r < 10'd2);
  wire [9:0] word0_o = !de_r ? ctrl0 : ((lit && !marker) ? WHITE : BLACK);
  wire [9:0] word1_o = !de_r ? CTRL00 : ((lit || marker) ? WHITE : BLACK);
  wire [9:0] word2_o = marker ? BLACK : word1_o;
`else
  wire [9:0] word0_o = !de_r ? ctrl0 : (lit ? WHITE : BLACK);
  wire [9:0] word1_o = !de_r ? CTRL00 : (lit ? WHITE : BLACK);
  wire [9:0] word2_o = word1_o;
`endif
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
    px_r <= px;
    py_r <= py;
    rram_q <= rram;
    status_q <= status;
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
`ifdef VIDEO_DOCK
    if (hx == 11'd1343) begin
      hx <= 11'd0;
      if (vy == 10'd805)
        vy <= 10'd0;
      else
        vy <= vy + 10'd1;
    end else begin
      hx <= hx + 11'd1;
    end
`else
    if (hx == 10'd857) begin
      hx <= 10'd0;
      if (vy == 10'd524)
        vy <= 10'd0;
      else
        vy <= vy + 10'd1;
    end else begin
      hx <= hx + 10'd1;
    end
`endif
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
