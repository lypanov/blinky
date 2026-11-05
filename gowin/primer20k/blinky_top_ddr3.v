// Primer 20K Dock wrapper. Fetch stays in block RAM. Loads and stores
// go through the DDR3 controller that already initializes the H5TQ1G63
// on this board. The CPU and the bridge run on pclk (387 MHz / 4).
//
// Dock user LEDs are active-low. CPU io_led is active-high, so invert
// onto L14. That is the only LED in the webcam cluster that moves.
// A failed prologue compare leaves it dark. UART TX is M11.
// HDMI, JTAG, and MSPI stay off this design.
//
// SRAM-load only. Do not flash.
//
// The command-port proof (define DDR3_PORT_TEST) blinked L14 at
// 0.720844 Hz. This build is the CPU prologue. The steady blink is
// the Blink3 body after every compare difference is zero.
//
// Each command now waits out the port-test pair (16 clocks, a refresh,
// 16 clocks) before the next one, so the 0.538222 Hz fit does not apply.
// Verilator, N = 5, 32, 128, 512, 1024, periods exact:
//   pclk/edge = 576*N + 788
// N = 262144 is 150995732 controller clocks per edge.
//   edge = 96750000/150995732 = 0.640747 Hz
//   full blink = 0.320373 Hz, 93.641 frames at 30 fps
// A corrupt read leaves the pin dark. Locked before the SRAM load.

module blinky_top_ddr3 (
  input  Clock,
  output IO_voltage,
  output [4:0] led,
  output [13:0] DDR3_A,
  output [2:0]  DDR3_BA,
  output        DDR3_nRAS,
  output        DDR3_nCAS,
  output        DDR3_nWE,
  output        DDR3_nCS,
  output        DDR3_CK,
  output        DDR3_CKE,
  output        DDR3_nRESET,
  output [1:0]  DDR3_DM,
  output        DDR3_ODT,
  inout  [15:0] DDR3_DQ,
  inout  [1:0]  DDR3_DQS,
  output        uart_tx
);
  wire fclk;
  wire pclk;
  wire cpu_clk;
  wire ck;
  wire pll_lock;
  wire [15:0] unused_deadbeef;
  wire [2:0]  unused_addr;
  wire        cpu_led;
  wire [31:0] cpu_pc;
  wire [31:0] cpu_r0, cpu_r4, cpu_r5, cpu_r7, cpu_r8, cpu_r9;
  wire [15:0] cpu_mask;
  wire        unused_uart_tx;

  wire        ddr_rd;
  wire        ddr_wr;
  wire        ddr_refresh;
  wire [25:0] ddr_addr;
  wire [15:0] ddr_din;
  wire [15:0] ddr_dout;
  wire [127:0] ddr_dout128;
  wire        ddr_ready;
  wire        ddr_busy;
  wire        ddr_resetn;
  wire        write_level_done;
  wire        read_calib_done;
  wire [7:0]  unused_wstep;
  wire [7:0]  wstep_run;
  wire [7:0]  wstep1;
  wire [1:0]  unused_rclkpos;
  wire [2:0]  unused_rclksel;
  wire [63:0] unused_debug;

  ddr3_pll u_pll (
    .clkin   (Clock),
    .reset   (1'b0),
    .clkout  (fclk),
    .clkoutp (ck),
    .clkoutd (pclk),
    .lock    (pll_lock)
  );

  // CPU is pclk/4. The divider runs as soon as the PLL locks, so the
  // CPU clock is already toggling while reset is held for calibration.
  GowinClkDiv u_div (
    .HCLKIN (pclk),
    .RESETN (pll_lock),
    .CALIB  (1'b0),
    .CLKOUT (cpu_clk)
  );

  // The pattern program starts only after read calibration. Until then
  // the blinking LED stays dark, which is the failure state. Reset is
  // released on cpu_clk so the CPU actually clocks the reset in.
  reg [1:0] cpu_rst_sync = 2'b11;
  always @(posedge cpu_clk or negedge pll_lock) begin
    if (!pll_lock)
      cpu_rst_sync <= 2'b11;
    else
      cpu_rst_sync <= {cpu_rst_sync[0], !read_calib_done};
  end
  wire cpu_reset = cpu_rst_sync[1];

  wire port_passed;
  wire port_failed;
  wire port_done;
  wire port_noready;
  wire [1:0] port_edge;
  wire [15:0] port_s0, port_s1, port_s2;

`ifdef DDR3_PORT_TEST
  reg        ctrl_resetn = 1'b0;
  reg        pass_sticky = 1'b0;
  assign ddr_resetn = pll_lock & ctrl_resetn;

  ddr3_port_test #(.WORDS(64)) u_port (
    .clk        (pclk),
    .resetn     (ddr_resetn),
    .calib      (read_calib_done),
    .rd         (ddr_rd),
    .wr         (ddr_wr),
    .refresh    (ddr_refresh),
    .addr       (ddr_addr),
    .din        (ddr_din),
    .dout       (ddr_dout),
    .data_ready (ddr_ready),
    .busy       (ddr_busy),
    .passed     (port_passed),
    .failed     (port_failed),
    .done       (port_done),
    .edge_sel   (port_edge),
    .noready    (port_noready),
    .samp0      (port_s0),
    .samp1      (port_s1),
    .samp2      (port_s2)
  );

  // Retry the controller the way NESTang does after a failed init.
  // Hold reset long enough for the result line to leave the UART, then
  // let the controller run its own 500 us CKE wait again. Four attempts.
  localparam [1:0] R_RUN = 2'd0, R_RST = 2'd1, R_HOLD = 2'd2;
  reg [1:0]  rstate = R_RUN;
  reg [1:0]  tries = 2'd0;
  reg [18:0] rst_cnt = 19'd0;
  reg [21:0] wait_cnt = 22'd0;

  reg        sending = 1'b0;
  reg        pend_boot = 1'b1;
  reg        pend_cal = 1'b0;
  reg        pend_res = 1'b0;
  reg        pend_w = 1'b0;
  reg [1:0]  kind = 2'd0;
  reg [4:0]  bi = 5'd0;
  reg        tx_we = 1'b0;
  reg [7:0]  tx_data = 8'h00;
  reg        calib_d = 1'b0;
  reg        done_d = 1'b0;
  reg        cap_pass = 1'b0;
  reg        cap_noready = 1'b0;
  reg [1:0]  cap_edge = 2'd0;
  reg [1:0]  cap_try = 2'd0;
  reg [15:0] cap_addr = 16'd0;
  reg [15:0] cap0 = 16'd0;
  reg [15:0] cap1 = 16'd0;
  reg [15:0] cap2 = 16'd0;
  wire       uart_busy;
  wire       last = (kind == 2'd3) ? (bi == 5'd25) : (bi == 5'd1);

  function [7:0] hexdig;
    input [3:0] n;
    begin
      hexdig = (n < 4'd10) ? (8'h30 + {4'b0, n}) : (8'h37 + {4'b0, n});
    end
  endfunction

  reg [7:0] emit;
  always @* begin
    emit = "\n";
    if (kind != 2'd3) begin
      if (bi == 5'd0) begin
        if (kind == 2'd0)
          emit = "B";
        else if (kind == 2'd1)
          emit = "C";
        else
          emit = "W";
      end
    end else begin
      case (bi)
        5'd0: emit = cap_noready ? "N" : (cap_pass ? "P" : "F");
        5'd1, 5'd6, 5'd11, 5'd16, 5'd21, 5'd23: emit = " ";
        5'd2: emit = hexdig(cap_addr[15:12]);
        5'd3: emit = hexdig(cap_addr[11:8]);
        5'd4: emit = hexdig(cap_addr[7:4]);
        5'd5: emit = hexdig(cap_addr[3:0]);
        5'd7: emit = hexdig(cap0[15:12]);
        5'd8: emit = hexdig(cap0[11:8]);
        5'd9: emit = hexdig(cap0[7:4]);
        5'd10: emit = hexdig(cap0[3:0]);
        5'd12: emit = hexdig(cap1[15:12]);
        5'd13: emit = hexdig(cap1[11:8]);
        5'd14: emit = hexdig(cap1[7:4]);
        5'd15: emit = hexdig(cap1[3:0]);
        5'd17: emit = hexdig(cap2[15:12]);
        5'd18: emit = hexdig(cap2[11:8]);
        5'd19: emit = hexdig(cap2[7:4]);
        5'd20: emit = hexdig(cap2[3:0]);
        5'd22: emit = 8'h30 + {6'b0, cap_edge};
        5'd24: emit = 8'h30 + {6'b0, cap_try};
        default: emit = "\n";
      endcase
    end
  end

  ddr3_uart_tx #(.CLKS_PER_BIT(840)) u_uart (
    .clk    (pclk),
    .resetn (pll_lock),
    .data   (tx_data),
    .we     (tx_we),
    .tx     (uart_tx),
    .busy   (uart_busy)
  );

  always @(posedge pclk or negedge pll_lock) begin
    if (!pll_lock) begin
      ctrl_resetn <= 1'b0;
      pass_sticky <= 1'b0;
      rstate <= R_RUN;
      tries <= 2'd0;
      rst_cnt <= 19'd0;
      wait_cnt <= 22'd0;
      sending <= 1'b0;
      pend_boot <= 1'b1;
      pend_cal <= 1'b0;
      pend_res <= 1'b0;
      pend_w <= 1'b0;
      kind <= 2'd0;
      bi <= 5'd0;
      tx_we <= 1'b0;
      calib_d <= 1'b0;
      done_d <= 1'b0;
    end else begin
      tx_we <= 1'b0;
      calib_d <= read_calib_done;
      done_d <= port_done;
      if (port_passed)
        pass_sticky <= 1'b1;
      if (read_calib_done && !calib_d)
        pend_cal <= 1'b1;
      if (port_done && !done_d) begin
        pend_res <= 1'b1;
        cap_pass <= port_passed;
        cap_noready <= port_noready;
        cap_edge <= port_edge;
        cap_try <= tries;
        cap_addr <= ddr_addr[15:0];
        cap0 <= port_s0;
        cap1 <= port_s1;
        cap2 <= port_s2;
      end

      if (!sending) begin
        if (pend_boot) begin
          sending <= 1'b1;
          kind <= 2'd0;
          bi <= 5'd0;
          pend_boot <= 1'b0;
        end else if (pend_cal) begin
          sending <= 1'b1;
          kind <= 2'd1;
          bi <= 5'd0;
          pend_cal <= 1'b0;
        end else if (pend_res) begin
          sending <= 1'b1;
          kind <= 2'd3;
          bi <= 5'd0;
          pend_res <= 1'b0;
        end else if (pend_w) begin
          sending <= 1'b1;
          kind <= 2'd2;
          bi <= 5'd0;
          pend_w <= 1'b0;
        end
      end else if (!uart_busy && !tx_we) begin
        tx_data <= emit;
        tx_we <= 1'b1;
        if (last)
          sending <= 1'b0;
        else
          bi <= bi + 5'd1;
      end

      case (rstate)
        R_RUN: begin
          ctrl_resetn <= 1'b1;
          if (pass_sticky || port_passed)
            rstate <= R_HOLD;
          else if (port_done && port_failed) begin
            if (tries == 2'd3)
              rstate <= R_HOLD;
            else begin
              tries <= tries + 2'd1;
              rstate <= R_RST;
              rst_cnt <= 19'd300000;
              ctrl_resetn <= 1'b0;
            end
          end else if (wait_cnt == 22'h3FFFFF) begin
            pend_w <= 1'b1;
            if (tries == 2'd3)
              rstate <= R_HOLD;
            else begin
              tries <= tries + 2'd1;
              rstate <= R_RST;
              rst_cnt <= 19'd300000;
              ctrl_resetn <= 1'b0;
            end
          end else
            wait_cnt <= wait_cnt + 22'd1;
        end
        R_RST: begin
          ctrl_resetn <= 1'b0;
          if (rst_cnt != 19'd0)
            rst_cnt <= rst_cnt - 19'd1;
          else if (!sending && !pend_res && !pend_w && !tx_we && !uart_busy) begin
            rstate <= R_RUN;
            wait_cnt <= 22'd0;
          end
        end
        default: begin
          ctrl_resetn <= 1'b1;
        end
      endcase
    end
  end
`else
  assign ddr_resetn = pll_lock;
  assign port_passed = 1'b0;
  assign port_failed = 1'b0;
  assign port_done = 1'b0;
  assign port_noready = 1'b0;
  assign port_edge = 2'd0;
  assign port_s0 = 16'd0;
  assign port_s1 = 16'd0;
  assign port_s2 = 16'd0;
  // One status line about twice a second, after the PLL locks.
  // H means the prologue hold. After the mask: the scanner index,
  // the column of the last read, then dq_in beats 0..7 as four
  // halfword pairs. Beat 0 is the byte the CPU is given today.
  reg        hold_seen = 1'b0;
  always @(posedge cpu_clk or negedge pll_lock) begin
    if (!pll_lock)
      hold_seen <= 1'b0;
    else if (cpu_pc[15:0] >= 16'h1390 && cpu_pc[15:0] < 16'h1400)
      hold_seen <= 1'b1;
  end
  reg [1:0] hold_sync = 2'b00;
  reg [15:0] pc_snap = 16'd0;
  always @(posedge pclk) begin
    hold_sync <= {hold_sync[0], hold_seen};
    pc_snap <= cpu_pc[15:0];
  end
  // dout128 is {beat0, ..., beat7} with beat 0 in the high half.
  // Repack so beat 0 is the low halfword. The CPU samples beat 0 only.
  reg [127:0] cap_beats = 128'd0;
  reg [25:0]  cap_addr = 26'd0;
  always @(posedge pclk) if (ddr_ready) begin
    cap_addr <= ddr_addr;
    cap_beats <= {ddr_dout128[15:0], ddr_dout128[31:16],
                  ddr_dout128[47:32], ddr_dout128[63:48],
                  ddr_dout128[79:64], ddr_dout128[95:80],
                  ddr_dout128[111:96], ddr_dout128[127:112]};
  end
  // The two repeated beat words are the last write instead. A store
  // that the DRAM did not take still shows up here.
  reg [25:0] wr_addr = 26'd0;
  reg [15:0] wr_data = 16'd0;
  always @(posedge pclk) if (ddr_wr) begin
    wr_addr <= ddr_addr;
    wr_data <= ddr_din;
  end

  function [7:0] hexdig;
    input [3:0] n;
    begin
      hexdig = (n < 4'd10) ? (8'h30 + {4'b0, n}) : (8'h37 + {4'b0, n});
    end
  endfunction

  function [31:0] hex16;
    input [15:0] v;
    begin
      hex16 = {hexdig(v[15:12]), hexdig(v[11:8]), hexdig(v[7:4]), hexdig(v[3:0])};
    end
  endfunction
  function [63:0] hex32;
    input [31:0] v;
    begin
      hex32 = {hex16(v[31:16]), hex16(v[15:0])};
    end
  endfunction

  // 76 bytes: calib, hold, PC, mask, index, column, two beat
  // pairs, the last write address and data, then the two write-level
  // steps. The beat pairs repeat, so the last two slots are the write.
  localparam integer UBYTES = 76;
  wire [UBYTES*8-1:0] msg = {
    read_calib_done ? "C" : ".",
    hold_sync[1] ? "H" : ".",
    hex16(pc_snap), " ",
    hex16(cpu_mask), " ",
    hex32(cpu_r5), " ",
    hex32({6'd0, cap_addr}), " ",
    hex32(cap_beats[31:0]), " ",
    hex32(cap_beats[63:32]), " ",
    hex32({6'd0, wr_addr}), " ",
    hex32({16'd0, wr_data}), " ",
    hex16({8'h00, unused_wstep}), " ",
    hex16({8'h00, wstep_run}), "\n"
  };
  reg [UBYTES*8-1:0] snap = {UBYTES{8'h00}};
  reg [25:0] rep = 26'd0;
  reg        boot_sent = 1'b0;
  reg        sending = 1'b0;
  reg [6:0]  bi = 7'd0;
  reg        tx_we = 1'b0;
  reg [7:0]  tx_data = 8'h00;
  wire       uart_busy;
  wire [7:0] emit = snap[(UBYTES-1-bi)*8 +: 8];
  ddr3_uart_tx #(.CLKS_PER_BIT(840)) u_uart (
    .clk    (pclk),
    .resetn (pll_lock),
    .data   (tx_data),
    .we     (tx_we),
    .tx     (uart_tx),
    .busy   (uart_busy)
  );
  always @(posedge pclk or negedge pll_lock) begin
    if (!pll_lock) begin
      rep <= 26'd0;
      boot_sent <= 1'b0;
      sending <= 1'b0;
      bi <= 4'd0;
      tx_we <= 1'b0;
    end else begin
      tx_we <= 1'b0;
      rep <= rep + 26'd1;
      if (!sending && (!boot_sent || rep == 26'd0)) begin
        boot_sent <= 1'b1;
        sending <= 1'b1;
        bi <= 7'd0;
        snap <= msg;
      end else if (sending && !uart_busy && !tx_we) begin
        tx_data <= emit;
        tx_we <= 1'b1;
        if (bi == UBYTES-1)
          sending <= 1'b0;
        else
          bi <= bi + 7'd1;
      end
    end
  end
  CPUMinimalWrapper u_cpu (
    .clock            (pclk),
    .reset            (cpu_reset),
    .io_cpu_clock     (cpu_clk),
    .io_led           (cpu_led),
    .io_pc            (cpu_pc),
    .io_r0            (cpu_r0),
    .io_r4            (cpu_r4),
    .io_r5            (cpu_r5),
    .io_r7            (cpu_r7),
    .io_r8            (cpu_r8),
    .io_r9            (cpu_r9),
    .io_dbgMask       (cpu_mask),
    .io_deadbeef      (unused_deadbeef),
    .io_addr          (unused_addr),
    .io_uart_rx       (1'b1),
    .io_uart_tx       (unused_uart_tx),
    .io_ddr_rd        (ddr_rd),
    .io_ddr_wr        (ddr_wr),
    .io_ddr_refresh   (ddr_refresh),
    .io_ddr_addr      (ddr_addr),
    .io_ddr_din       (ddr_din),
    .io_ddr_dout      (ddr_dout),
    .io_ddr_data_ready(ddr_ready),
    .io_ddr_busy      (ddr_busy),
    .io_ddr_calib     (read_calib_done)
  );
`endif

  ddr3_controller #(
    .ROW_WIDTH(13), .COL_WIDTH(10), .BANK_WIDTH(3)
  ) u_ddr3 (
    .DDR3_DQ      (DDR3_DQ),
    .DDR3_DQS     (DDR3_DQS),
    .DDR3_A       (DDR3_A[12:0]),
    .DDR3_BA      (DDR3_BA),
    .DDR3_nRAS    (DDR3_nRAS),
    .DDR3_nCAS    (DDR3_nCAS),
    .DDR3_nWE     (DDR3_nWE),
    .DDR3_nCS     (DDR3_nCS),
    .DDR3_CK      (DDR3_CK),
    .DDR3_CKE     (DDR3_CKE),
    .DDR3_nRESET  (DDR3_nRESET),
    .DDR3_DM      (DDR3_DM),
    .DDR3_ODT     (DDR3_ODT),
    .pclk         (pclk),
    .fclk         (fclk),
    .ck           (ck),
    .resetn       (ddr_resetn),
    .rd           (ddr_rd),
    .wr           (ddr_wr),
    .refresh      (ddr_refresh),
    .addr         (ddr_addr),
    .din          (ddr_din),
    .dout         (ddr_dout),
    .dout128      (ddr_dout128),
    .data_ready   (ddr_ready),
    .busy         (ddr_busy),
    .write_level_done(write_level_done),
    .wstep        (unused_wstep),
    .wstep_run    (wstep_run),
    .wstep1       (wstep1),
    .read_calib_done(read_calib_done),
    .rclkpos      (unused_rclkpos),
    .rclksel      (unused_rclksel),
    .debug        (unused_debug)
  );
  assign DDR3_A[13] = 1'b0;

`ifdef DDR3_PORT_TEST
  // L14 blinks at 0.720844 Hz only after a passing attempt. C13 stays
  // dark so it cannot be mistaken for that blink. A13 blinks at
  // 0.201166 Hz from the 27 MHz pin for the whole run.
  reg [26:0] pass_div = 27'd0;
  reg [26:0] alive_div = 27'd0;
  always @(posedge pclk) begin
    if (pass_sticky)
      pass_div <= pass_div + 27'd1;
  end
  always @(posedge Clock)
    alive_div <= alive_div + 27'd1;
  // cpu_clk has to stay in the netlist or the SDC's generated clock
  // has nothing to attach to. N16 is outside the webcam cluster.
  reg cpu_tick = 1'b0;
  always @(posedge cpu_clk)
    cpu_tick <= ~cpu_tick;
  assign IO_voltage = pass_sticky ? ~pass_div[26] : 1'b1;
  assign led[0] = 1'b1;
  assign led[1] = alive_div[26];
  assign led[2] = cpu_tick;
`else
  // L14 is the only moving LED the webcam cluster can see. C13 and A13
  // stay dark, so a PC divider cannot be reported as the proof blink.
  // cpu_led is 0 until every compare difference was zero, and then it
  // follows the Blink3 state. Failure leaves L14 off.
  assign IO_voltage = ~cpu_led;
  assign led[0] = 1'b1;
  assign led[1] = 1'b1;
  assign led[2] = 1'b1;
`endif
  assign led[3] = 1'b1;
  assign led[4] = 1'b1;
endmodule
