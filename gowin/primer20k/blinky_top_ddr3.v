// Primer 20K Dock wrapper. Fetch stays in block RAM. Loads and stores
// go through the DDR3 controller that already initializes the H5TQ1G63
// on this board. The CPU and the bridge run on pclk (387 MHz / 4).
//
// Dock user LEDs are active-low. CPU io_led is active-high, so invert
// onto L14. UART TX is M11, the Dock BL702 pin, and only the port
// test uses it. HDMI, JTAG, and MSPI stay off this design.
//
// SRAM-load only. Do not flash.

// Command-port proof. Pass blink is pclk/2^27 on L14:
//   96750000 / 134217728 = 0.720844 Hz
// and only after all 64 words match one sample edge. A13 is the 27 MHz
// pin divided the same way, 27000000 / 134217728 = 0.201166 Hz, so a
// configured FPGA is visible even when the compare fails.
`define DDR3_PORT_TEST

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
  wire        unused_uart_tx;

  wire        ddr_rd;
  wire        ddr_wr;
  wire        ddr_refresh;
  wire [25:0] ddr_addr;
  wire [15:0] ddr_din;
  wire [15:0] ddr_dout;
  wire        ddr_ready;
  wire        ddr_busy;
  wire        ddr_resetn;
  wire        write_level_done;
  wire        read_calib_done;
  wire [7:0]  unused_wstep;
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
  assign uart_tx = 1'b1;
  CPUMinimalWrapper u_cpu (
    .clock            (pclk),
    .reset            (cpu_reset),
    .io_cpu_clock     (cpu_clk),
    .io_led           (cpu_led),
    .io_pc            (cpu_pc),
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
    .data_ready   (ddr_ready),
    .busy         (ddr_busy),
    .write_level_done(write_level_done),
    .wstep        (unused_wstep),
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
  // Webcam cluster is L14 / C13 / A13. N16, N14, L16 are outside it.
  //   L14 = program LED, the only proof pin
  //   C13 = PC changing (bit 22)
  //   A13 = io_led edges (bit 14)
  reg [23:0] pc_div = 24'd0;
  reg [15:0] led_div = 16'd0;
  reg [31:0] pc_d = 32'd0;
  reg        led_d = 1'b0;
  always @(posedge cpu_clk) begin
    pc_d <= cpu_pc;
    led_d <= cpu_led;
    if (cpu_pc != pc_d)
      pc_div <= pc_div + 24'd1;
    if (cpu_led != led_d)
      led_div <= led_div + 16'd1;
  end
  assign IO_voltage = ~cpu_led;
  assign led[0] = pc_div[22];
  assign led[1] = led_div[14];
  assign led[2] = 1'b1;
`endif
  assign led[3] = 1'b1;
  assign led[4] = 1'b1;
endmodule
