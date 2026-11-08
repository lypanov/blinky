// Behavioural user side of Gowin's HyperRAM Memory Interface (IPUG944-2.1).
//
// The encrypted PHY (hpram_code_1N2A.v) cannot be simulated. This model
// implements the plain-Verilog user ports of HPRAM_TOP / Table 5-1 and the
// handshake in figures 4-6 (command), 4-7 (write data) and 4-11 (read data):
//
//   * cmd_en is a one-cycle pulse. While it is high, cmd and addr are valid.
//     cmd = 1 writes, cmd = 0 reads.
//   * Burst length is 16 bytes: four 32-bit beats. Write beat 0 is sampled
//     on the cmd_en cycle; beats 1..3 follow on the next three clocks.
//   * data_mask bit 0 means "write this byte". 0xF leaves the word unchanged.
//   * addr is a 16-bit-word address (byte address >> 1), 22 bits for 8 MB.
//     A 16-byte burst starts on an address whose low 3 bits are 0.
//   * rd_data_valid stays high for four clocks. Figure 4-11 shows a gap
//     after cmd_en and does not give its length. FIRST_VALID is the
//     countdown loaded on the cmd_en cycle, so the first valid is
//     FIRST_VALID+1 user clocks later.
//
//     FIRST_VALID = 12 (the default) puts that pulse 13 user clocks after
//     cmd_en, inside the Table 4-2 minimum of 15 user clocks between
//     commands (burst 16, memory clock <= 166 MHz). The bridge waits for
//     both, so this setting is limited by the command gap. It is the
//     model that predicted 0.520 Hz before the board was loaded.
//
//     FIRST_VALID = 13 delays the whole read burst by one user clock.
//     Every load then stalls one cycle past that gap. Stores do not,
//     because a write is released on the gap alone. This value was fitted
//     after the Nano 4K measured 0.500 Hz on the same bitstream. It is not
//     a pre-load prediction.
//   * init_calib rises and stays high. Real calibration is milliseconds;
//     INIT_CYCLES is short so a trace can show the stall. The blink rate
//     is measured after calibration on both sides.
//   * clk_out is the user clock. Here it is clk, which stands in for the
//     hardware clk_out (memory_clk / 2). memory_clk is accepted and unused.
//
// `define HYPER_CORRUPT makes every read return 0. The prologue must then
// keep the LED dark. Timing of rd_data_valid does not change.

`timescale 1ns/1ps

module HyperRamUserModel (
  input         clk,
  input         memory_clk,
  input         pll_lock,
  input         rst_n,
  input  [31:0] wr_data,
  output reg [31:0] rd_data,
  output reg    rd_data_valid,
  input  [21:0] addr,
  input         cmd,
  input         cmd_en,
  output reg    init_calib,
  output        clk_out,
  input  [3:0]  data_mask
);

  // 40960 words is 160 KB. The packed core ends just under 128 KB.
  // The flash bootstrap also parks the init stream at 0x20000, which
  // is the first byte past 32768 words. 10240 words stopped at 0x9FFC.
  localparam integer WORDS = 40960;
  localparam integer INIT_CYCLES = 64;
  // See the header. 12 is the pre-load model. 13 is the post-measurement fit.
  parameter integer FIRST_VALID = 12;
  localparam integer TCMD = 15;

  assign clk_out = clk;
  // The PHY consumes memory_clk. The user model is clocked by clk.
  wire unused_memory_clk = memory_clk;

  reg [31:0] mem [0:WORDS-1];
  integer mi;
  reg [31:0] init_fill;
  // The image stores only non-zero words. A zeroed model hides a board
  // whose HyperRAM powers up as ones: the descriptor's NIL links and the
  // string NULs that share a zero word never land.
  initial begin
    init_fill = 32'h0000_0000;
    if (!$value$plusargs("init_fill=%h", init_fill)) init_fill = 32'h0;
    for (mi = 0; mi < WORDS; mi = mi + 1)
      mem[mi] = init_fill;
  end

  reg [31:0] cycle;
  reg [31:0] last_cmd;
  reg        seen_cmd;
  reg [7:0]  fault;
  reg [7:0]  init_cnt;

  reg        wr_busy;
  reg [2:0]  wr_beat;
  reg [21:0] wr_base;
  // +late_last=N samples beat 3 N user clocks after the bridge presents
  // it. N=0 is the on-time model. The bridge holds that beat through the
  // command gap, so a late sample still writes the word.
  reg [7:0]  late_n;
  reg [7:0]  pend_wait;
  reg [21:0] pend_base;
  // +valid_stretch=N holds rd_data_valid for N clocks per beat. N=1 is
  // the PHY the bridge was written for. N=2 makes the bridge count two
  // beats per word, so a slot-3 load returns a different word.
  reg [3:0]  stretch;
  reg [3:0]  holdv;
  // +read_ones makes every load return 0xFFFFFFFF. A string compare
  // then never sees a zero byte and stays in the upper core.
  reg        read_ones;
  initial begin
    late_n = 8'h0;
    pend_wait = 8'h0;
    stretch = 4'h1;
    holdv = 4'h0;
    read_ones = 1'b0;
    if (!$value$plusargs("late_last=%d", late_n)) late_n = 8'h0;
    if (!$value$plusargs("valid_stretch=%d", stretch)) stretch = 4'h1;
    if (stretch == 4'h0) stretch = 4'h1;
    if ($test$plusargs("read_ones")) read_ones = 1'b1;
  end

  reg        rd_busy;
  reg [7:0]  rd_wait;
  reg [2:0]  rd_beat;
  reg [21:0] rd_base;

  task automatic apply_write;
    input [21:0] base;
    input [2:0]  beat;
    input [31:0] data;
    input [3:0]  mask;
    integer idx;
    reg [31:0] oldv;
    begin
      idx = (base >> 1) + beat;
      if (idx < 0 || idx >= WORDS) begin
        fault <= fault | 8'h04;
        $display("HYPER_RANGE_FAULT addr=%h beat=%0d", base, beat);
      end else begin
`ifndef HYPER_CORRUPT
        oldv = mem[idx];
        if (!mask[0]) oldv[7:0]   = data[7:0];
        if (!mask[1]) oldv[15:8]  = data[15:8];
        if (!mask[2]) oldv[23:16] = data[23:16];
        if (!mask[3]) oldv[31:24] = data[31:24];
        mem[idx] = oldv;
`endif
      end
    end
  endtask

  function [31:0] read_word;
    input [21:0] base;
    input [2:0]  beat;
    integer idx;
    begin
      idx = (base >> 1) + beat;
      if (idx < 0 || idx >= WORDS)
        read_word = 32'hEEEE_EEEE;
`ifdef HYPER_CORRUPT
      else
        read_word = 32'h0000_0000;
`else
      else if (read_ones)
        read_word = 32'hFFFF_FFFF;
      else
        read_word = mem[idx];
`endif
    end
  endfunction

  always @(posedge clk) begin
    if (!rst_n || !pll_lock) begin
      init_calib <= 1'b0;
      init_cnt <= 8'h0;
      rd_data_valid <= 1'b0;
      rd_data <= 32'h0;
      cycle <= 32'h0;
      seen_cmd <= 1'b0;
      last_cmd <= 32'h0;
      fault <= 8'h0;
      wr_busy <= 1'b0;
      pend_wait <= 8'h0;
      rd_busy <= 1'b0;
      wr_beat <= 3'h0;
      rd_beat <= 3'h0;
      rd_wait <= 8'h0;
      holdv <= 4'h0;
    end else begin
      cycle <= cycle + 32'h1;
      rd_data_valid <= 1'b0;

      if (!init_calib) begin
        if (init_cnt == INIT_CYCLES)
          init_calib <= 1'b1;
        else
          init_cnt <= init_cnt + 8'h1;
      end else begin
        if (pend_wait != 8'h0) begin
          if (pend_wait == 8'h1)
            apply_write(pend_base, 3'd3, wr_data, data_mask);
          pend_wait <= pend_wait - 8'h1;
        end

        if (wr_busy) begin
          if (late_n != 8'h0 && wr_beat == 3'd3) begin
            pend_base <= wr_base;
            pend_wait <= late_n;
            wr_busy <= 1'b0;
          end else begin
            apply_write(wr_base, wr_beat, wr_data, data_mask);
            if (wr_beat == 3'd3)
              wr_busy <= 1'b0;
            else
              wr_beat <= wr_beat + 3'd1;
          end
        end

        if (rd_busy) begin
          if (rd_wait != 8'h0) begin
            rd_wait <= rd_wait - 8'h1;
          end else begin
            rd_data <= read_word(rd_base, rd_beat);
            rd_data_valid <= 1'b1;
            if (holdv + 4'h1 < stretch) begin
              holdv <= holdv + 4'h1;
            end else begin
              holdv <= 4'h0;
              if (rd_beat == 3'd3)
                rd_busy <= 1'b0;
              else
                rd_beat <= rd_beat + 3'd1;
            end
          end
        end

        if (cmd_en) begin
          if (wr_busy || rd_busy) begin
            fault <= fault | 8'h01;
            $display("HYPER_TIMING_FAULT overlap cycle=%0d", cycle);
          end else if (seen_cmd && (cycle - last_cmd) < TCMD) begin
            fault <= fault | 8'h02;
            $display("HYPER_TIMING_FAULT gap %0d cycle=%0d", cycle - last_cmd, cycle);
          end else begin
            seen_cmd <= 1'b1;
            last_cmd <= cycle;
            if (cmd) begin
              apply_write(addr, 3'd0, wr_data, data_mask);
              wr_base <= addr;
              wr_beat <= 3'd1;
              wr_busy <= 1'b1;
            end else begin
              rd_base <= addr;
              rd_beat <= 3'd0;
              rd_wait <= FIRST_VALID;
              rd_busy <= 1'b1;
            end
          end
        end
      end
    end
  end

endmodule
