// Behavioural stand-in for ddr3_controller's command port.
//
// The PHY (OSER8/DQS/DLL) is not simulated. What is simulated is the
// post-calibration command timing of that controller, DDR3-800, and the
// command-port consequences of DM, beat select, and per-lane write delay.
//
//   * rd/wr/refresh are one-cycle pulses, sampled when busy is low.
//   * addr is a 16-bit-word address. din/dout are that one halfword.
//     column = addr[9:0], row = addr[22:10], bank = addr[25:23].
//     The array is 4096 halfwords (addr[11:0]), two bytes per column.
//   * A read presents dout with data_ready nine clocks after the pulse,
//     and drops busy on the tenth clock. A write or a refresh drops
//     busy on the sixth clock.
//   * calib rises after INIT_CYCLES and stays high.
//
// A halfword write is one BC4 beat. DM unmasks that beat and drives din
// onto both lanes. It does not mask one byte of the x16 beat. The bridge
// has already merged a byte store into din. Both lanes have to agree on
// the same beat or the merged byte does not come back.
//
// Write delay, named as the controller's WSTEP. 10 is the passing eye
// for that lane (the forced wstep_run). The other lane defaults to 10
// as well, which is "lane 1 matched".
//
//   * step 10: the beat lands on the addressed column.
//   * step 9: one beat early. The first word of a BC4 group is written
//     into both words of the group, and the second word does not replace
//     it. An odd column then reads back the even column on that lane.
//     Both lanes at 9 is the odd-column pattern sum AAAAAAAA with the
//     single-word checks still matching (mask F0). Lane 1 alone at 9
//     leaves lane 0's sum bytes at FF and lane 1's at AA (AAFFAAFF).
//   * step 11: one beat late. The second word of the group overwrites
//     both words on that lane.
//   * any other step: that lane's byte is stored (step-10) columns away.
//
// +ddr3_nohold turns off the read-FIFO reset. A column with addr[1] set
// returns the even column, even when the write landed on the odd one.
// +ddr3_nowload omits the WLOADN reload. HOLD stops the write clock, and
// without the reload a write that follows a read lands two columns later.
// +ddr3_dm_all unmasks all four BC4 beats. +ddr3_dm_lane0 / +ddr3_dm_lane1
// write only that lane. +ddr3_corrupt returns 0. +ddr3_late keeps dout
// one clock behind data_ready.

`timescale 1ns/1ps

module Ddr3UserModel (
  input              clk,
  input              rst_n,
  input              rd,
  input              wr,
  input              refresh,
  input      [25:0]  addr,
  input      [15:0]  din,
  output reg [15:0]  dout,
  output reg         data_ready,
  output reg         busy,
  output reg         calib
);
  localparam integer WORDS = 4096;
  localparam integer INIT_CYCLES = 64;
  localparam integer GROUPS = WORDS / 4;

  reg [7:0] lane0 [0:WORDS-1];
  reg [7:0] lane1 [0:WORDS-1];
  // Set once the even word of this BC4 group has been written on that lane
  // under the early-eye rule. The odd word is then dropped.
  reg       seen0 [0:GROUPS-1];
  reg       seen1 [0:GROUPS-1];
  reg [15:0] init_cnt;
  reg [15:0] hold;
  reg [4:0]  cycle;
  reg [1:0]  op;       // 0 idle, 1 read, 2 write, 3 refresh
  reg        corrupt;
  reg        late;
  reg        dout_pend;
  reg        hold_en;
  reg        wloadn_en;
  reg        write_skew;   // a read stopped the write clock and nothing reloaded it
  reg [1:0]  dm_mode;      // 0 one beat, 1 all four beats, 2 lane0 only, 3 lane1 only
  integer    lane0_mode;   // 0 good, 1 early, 2 late, 3 shift
  integer    lane1_mode;
  integer    lane0_sh;
  integer    lane1_sh;
  integer    i;

  task automatic eye_from_step;
    input integer step;
    output integer mode;
    output integer sh;
    begin
      if (step == 10) begin
        mode = 0;
        sh = 0;
      end else if (step == 9) begin
        mode = 1;
        sh = 0;
      end else if (step == 11) begin
        mode = 2;
        sh = 0;
      end else begin
        mode = 3;
        sh = step - 10;
      end
    end
  endtask

  task automatic put_byte;
    input integer col;
    input integer lane;
    input [7:0] bytev;
    begin
      if (col >= 0 && col < WORDS) begin
        if (lane == 0)
          lane0[col] = bytev;
        else
          lane1[col] = bytev;
      end
    end
  endtask

  task automatic apply_lane;
    input integer col;
    input integer lane;
    input [7:0] bytev;
    input integer mode;
    input integer sh;
    integer dest;
    integer g;
    integer partner;
    reg drop;
    begin
      if (col >= 0 && col < WORDS) begin
        g = col >> 2;
        partner = col ^ 2;
        if (mode == 0) begin
          put_byte(col, lane, bytev);
        end else if (mode == 1) begin
          // Early eye: the even word fills both words; the odd word does not.
          if ((col & 2) == 0) begin
            put_byte(col, lane, bytev);
            put_byte(partner, lane, bytev);
            if (lane == 0)
              seen0[g] = 1'b1;
            else
              seen1[g] = 1'b1;
          end else begin
            drop = (lane == 0) ? seen0[g] : seen1[g];
            if (!drop)
              put_byte(col, lane, bytev);
          end
        end else if (mode == 2) begin
          // Late eye: the odd word overwrites both words of the group.
          put_byte(col, lane, bytev);
          if ((col & 2) != 0)
            put_byte(partner, lane, bytev);
        end else begin
          dest = col + sh;
          put_byte(dest, lane, bytev);
        end
      end
    end
  endtask

  function [15:0] read_half;
    input integer col;
    integer c;
    begin
      c = col;
      // No HOLD: the read FIFO was not reset, so the odd word of the
      // group comes back as the even word.
      if (!hold_en && (c & 2))
        c = c & ~2;
      if (c < 0 || c >= WORDS)
        read_half = 16'h0000;
      else
        read_half = {lane1[c], lane0[c]};
    end
  endfunction

  initial begin
    corrupt = 1'b0;
    late = 1'b0;
    dout_pend = 1'b0;
    hold_en = 1'b1;
    wloadn_en = 1'b1;
    write_skew = 1'b0;
    dm_mode = 2'd0;
    dout = 16'd0;
    data_ready = 1'b0;
    busy = 1'b0;
    calib = 1'b0;
    op = 2'd0;
    cycle = 5'd0;
    init_cnt = 16'd0;
    hold = 16'd0;
    for (i = 0; i < WORDS; i = i + 1) begin
      lane0[i] = 8'd0;
      lane1[i] = 8'd0;
    end
    for (i = 0; i < GROUPS; i = i + 1) begin
      seen0[i] = 1'b0;
      seen1[i] = 1'b0;
    end
    if ($test$plusargs("ddr3_corrupt"))
      corrupt = 1'b1;
    if ($test$plusargs("ddr3_late"))
      late = 1'b1;
    if ($test$plusargs("ddr3_nohold"))
      hold_en = 1'b0;
    if ($test$plusargs("ddr3_nowload"))
      wloadn_en = 1'b0;
    if ($test$plusargs("ddr3_dm_all"))
      dm_mode = 2'd1;
    if ($test$plusargs("ddr3_dm_lane0"))
      dm_mode = 2'd2;
    if ($test$plusargs("ddr3_dm_lane1"))
      dm_mode = 2'd3;
    begin : eye_init
      integer s0, s1;
      s0 = 10;
      s1 = 10;
      if (!$value$plusargs("ddr3_lane0=%d", s0))
        s0 = 10;
      if (!$value$plusargs("ddr3_lane1=%d", s1))
        s1 = 10;
      eye_from_step(s0, lane0_mode, lane0_sh);
      eye_from_step(s1, lane1_mode, lane1_sh);
      $display("DDR3 model hold=%0d wloadn=%0d dm=%0d lane0=%0d(mode %0d sh %0d) lane1=%0d(mode %0d sh %0d) corrupt=%0d late=%0d",
               hold_en, wloadn_en, dm_mode, s0, lane0_mode, lane0_sh, s1, lane1_mode, lane1_sh, corrupt, late);
    end
  end

  wire in_range = addr[25:12] == 14'd0;
  wire [11:0] idx = addr[11:0];

  integer col;
  integer beat;
  integer base;
  always @(posedge clk) begin
    data_ready <= 1'b0;
    if (!rst_n) begin
      busy <= 1'b0;
      calib <= 1'b0;
      op <= 2'd0;
      cycle <= 5'd0;
      init_cnt <= 16'd0;
      dout <= 16'd0;
      write_skew <= 1'b0;
      for (i = 0; i < GROUPS; i = i + 1) begin
        seen0[i] = 1'b0;
        seen1[i] = 1'b0;
      end
    end else begin
      if (!calib) begin
        if (init_cnt == INIT_CYCLES)
          calib <= 1'b1;
        else
          init_cnt <= init_cnt + 16'd1;
      end

      if (op != 2'd0) begin
        cycle <= cycle + 5'd1;
        // Read: the controller schedules data_ready when cycle==8, so
        // the pulse is visible the following clock (cycle value 9).
        if (op == 2'd1 && cycle == 5'd8) begin
          data_ready <= 1'b1;
          // +ddr3_late keeps dout one clock behind data_ready, which is
          // the skew the PHY can show and the behavioural model otherwise hides.
          if (!late)
            dout <= corrupt ? 16'd0 : hold;
          else
            dout_pend <= 1'b1;
        end
        if (dout_pend) begin
          dout <= corrupt ? 16'd0 : hold;
          dout_pend <= 1'b0;
        end
        if ((op == 2'd1 && cycle == 5'd9) ||
            (op != 2'd1 && cycle == 5'd5)) begin
          busy <= 1'b0;
          op <= 2'd0;
          // The read's last cycle is the WLOADN pulse. Its falling edge
          // reloads WSTEP. Without that pulse the write clock stays where
          // HOLD left it, and later writes land two columns high.
          if (op == 2'd1)
            write_skew <= ~wloadn_en;
        end
      end else if (calib && !busy && (rd || wr || refresh)) begin
        busy <= 1'b1;
        cycle <= 5'd1;
        if (rd) begin
          op <= 2'd1;
          if (!in_range) begin
            hold <= 16'd0;
            $display("DDR3_RANGE_FAULT read addr=%h", addr);
          end else
            hold <= read_half(idx);
        end else if (wr) begin
          op <= 2'd2;
          col = idx;
          if (write_skew)
            col = col + 2;
          if (!in_range) begin
            $display("DDR3_RANGE_FAULT write addr=%h", addr);
          end else if (dm_mode == 2'd1) begin
            // Every beat of the BC4 group takes din. The neighbour word
            // in the same burst does not survive.
            base = col & ~3;
            for (beat = 0; beat < 4; beat = beat + 1) begin
              put_byte(base + beat, 0, din[7:0]);
              put_byte(base + beat, 1, din[15:8]);
            end
          end else if (dm_mode == 2'd2) begin
            put_byte(col, 0, din[7:0]);
          end else if (dm_mode == 2'd3) begin
            put_byte(col, 1, din[15:8]);
          end else begin
            apply_lane(col, 0, din[7:0], lane0_mode, lane0_sh);
            apply_lane(col, 1, din[15:8], lane1_mode, lane1_sh);
          end
        end else begin
          op <= 2'd3;
        end
      end
    end
  end
endmodule
