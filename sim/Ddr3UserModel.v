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
// Write delay is the controller's WSTEP, compared with +ddr3_center.
// The default center is 10. That is the ALU place and the reader place
// that passed: both lanes programmed to step 10. +ddr3_center does not
// change the step a bitstream writes. It says which programmed step is
// the eye on that route.
//
// +ddr3_place_fetch is the absolute-step image, before backoff.
// The model reads the lane numbers. Codes 9 and 10 were both
// measured as offset +1 (R5 AAAAAAAA, R9 55555536, mask F0). The
// model reads the step. Any other code on that image is step-10.
// +ddr3_fetch_eye is the fetch place. With no edge plusargs the
// centers are lane 0 = 11 and lane 1 = 7, the calibration whose
// edges were 000C and 000A. +ddr3_edge0 and +ddr3_edge1 move those
// centers to edge minus the RTL backoff (1 and 3). The reload on
// the Dock is edges 000D and 000A, steps 000C and 0007, and that
// pair is offset 0 only when the edges are supplied. Without them
// lane 0 at 12 is offset +1 (R5 FFAAFFAA). Lane 0 at 10 with lane 1
// at 7 is one below (R5 00550054). Lane 1 at 6 with lane 0 at 11 is
// one below on lane 1 (R5 550054FF). Lane 1 at 8 with lane 0 at 11
// is the even-word alias (R5 AAFFAAFF). Those are different rows.
// +ddr3_fetch_split is an earlier image's pin split (DQ1 one column
// early, DQ13 in the even-word alias, R5 DFFFDFFF). That image
// printed the same codes 000B/0007. It is not offset 0.
// +ddr3_pd_eye is the P/D-chain place. The prologue sum runs before
// the chain, on the same BC4 writes as the fetch image. The pins
// agree. Lane 0 steps 10 and 11, and lane 1 steps 5, 6, and 7, are
// the whole-column even-word alias (R5 AAAAAAAA, R9 55555536, mask
// F0). No measured code is offset 0. There is no write-level input.
// The edges on the last two loads were 000D and 000A. Lane 0's
// edge was 000C on the first load.
//
// Forcing both lanes to 9 on the rebuilt reader place is not this
// offset 0. The Dock read the sentinel as 0x2505A5A5 (DQ5, DQ7 and DQ15
// clear on beat 1, beat 0 intact) and summed the pattern to AFF0B9CF.
// That is a split inside one step: the pins do not agree. A whole
// column, a per-beat bitwise mask, and a per-pin slide of one or two
// columns were checked against that UART; none of them produce the two
// sums and the sentinel together. This model still has only the whole
// column. Offset 0 means every pin landed on the addressed column.
//
// The later step sweep (both lanes 6..16, then lane 1 held at its
// write-level result 0x0A and at 9 and 0x0B) is not a set of offsets
// either. Both lanes at step 10 are two of its rows, and those rows
// disagree (R5 0C0D0D9D mask 70, and R5 54F854F7 mask F0). The sweep
// leaves the array in place, so a miss keeps the previous trial's
// bytes. Fresh-array and kept-array checks of a column shift, a
// per-beat grab, a one-column pin slip, a BC4 beat remix, and a
// per-byte bit map do not produce 54F854F7, AFF7AFF7, or 0C0D0D9D.
// There is no plusarg for that table.
//
// A cold prologue with both lanes programmed to step 10, after
// DDR3_nRESET, is a pin split rather than that whole-column alias.
// +ddr3_pin_even is a 16-bit mask: bit 0 is DQ0, bit 8 is DQ8. A set
// bit uses the even-word broadcast; a clear bit stores on the
// addressed column. +ddr3_odd_clear is the same numbering. On the
// high half of an odd column, a 0 on one of those pins clears the
// bit the broadcast left behind. Mask 20FF and odd-clear bit 1
// (DQ1) is this cold line: R5 DFAADFAA, R9 20532036, mask F0.
// The step plusargs do not apply while the pin mask is set.
//
//   * offset 0 (programmed == center): the beat lands on the column.
//   * offset +1: one step above the eye, toward the write-level edge.
//     The even word of a BC4 group is written into both words, and the
//     odd word does not replace it. An odd column then reads back the
//     even column on that lane. Both lanes there is the pattern sum
//     AAAAAAAA, and the single-word checks still match (mask F0).
//   * offset -1: one step below the eye. The odd word overwrites both
//     words of the group on that lane.
//   * any other offset: that lane's byte is stored that many columns away.
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
  integer    lane0_mode;   // 0 good, 1 one above, 2 one below, 3 shift
  integer    lane1_mode;
  integer    lane0_sh;
  integer    lane1_sh;
  integer    center;       // programmed step the data eye is centered on
  integer    i;
  reg        pin_even_en;
  reg        fetch_split;  // DQ1 one column early, DQ13 even-word alias
  reg [15:0] pin_even;     // bit 0 = DQ0 ... bit 15 = DQ15, even-word broadcast
  reg [15:0] odd_clear;    // same numbering; a 0 on the odd word's high half clears

  task automatic eye_from_offset;
    input integer off;
    output integer mode;
    output integer sh;
    begin
      if (off == 0) begin
        mode = 0;
        sh = 0;
      end else if (off == 1) begin
        // One step above the eye: even word fills the BC4 group.
        mode = 1;
        sh = 0;
      end else if (off == -1) begin
        // One step below the eye: odd word overwrites the group.
        mode = 2;
        sh = 0;
      end else begin
        mode = 3;
        sh = off;
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
          // One step above the eye: the even word fills both words.
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
          // One step below the eye: the odd word overwrites both words.
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

  // One DQ pin. even copies the even word onto its partner. On the high
  // half of the odd word, a clear pin written as 0 still wins.
  task automatic put_bit;
    input integer col;
    input integer lane;
    input integer bitn;
    input val;
    reg [7:0] tmp;
    begin
      if (col >= 0 && col < WORDS) begin
        if (lane == 0)
          tmp = lane0[col];
        else
          tmp = lane1[col];
        tmp[bitn] = val;
        if (lane == 0)
          lane0[col] = tmp;
        else
          lane1[col] = tmp;
      end
    end
  endtask

  task automatic apply_masked;
    input integer col;
    input integer lane;
    input [7:0] bytev;
    integer bitn;
    integer g;
    integer partner;
    integer idx;
    reg even;
    reg clr;
    reg val;
    reg drop;
    begin
      if (col >= 0 && col < WORDS) begin
        g = col >> 2;
        partner = col ^ 2;
        for (bitn = 0; bitn < 8; bitn = bitn + 1) begin
          idx = lane * 8 + bitn;
          even = pin_even[idx];
          clr = odd_clear[idx];
          val = bytev[bitn];
          if (!even) begin
            put_bit(col, lane, bitn, val);
          end else if ((col & 2) == 0) begin
            put_bit(col, lane, bitn, val);
            put_bit(partner, lane, bitn, val);
            if (lane == 0)
              seen0[g] = 1'b1;
            else
              seen1[g] = 1'b1;
          end else begin
            if (clr && (col & 1) && !val)
              put_bit(col, lane, bitn, 1'b0);
            else begin
              drop = (lane == 0) ? seen0[g] : seen1[g];
              if (!drop)
                put_bit(col, lane, bitn, val);
            end
          end
        end
      end
    end
  endtask

  // Earlier image that printed DFFFDFFF at steps 0007 000B. DQ1 lands
  // one column early. Not offset 0, and not the pass program.
  // DQ13 takes the even word of the BC4 group on both words. Every
  // other pin writes the addressed column. The sentinel bytes are
  // equal across a group, so DQ13's alias does not move it.
  task automatic apply_fetch_split;
    input integer col;
    input integer lane;
    input [7:0] bytev;
    integer bitn;
    integer g;
    integer partner;
    reg val;
    begin
      if (col >= 0 && col < WORDS) begin
        g = col >> 2;
        partner = col ^ 2;
        for (bitn = 0; bitn < 8; bitn = bitn + 1) begin
          val = bytev[bitn];
          if (lane == 0 && bitn == 1) begin
            put_bit(col - 1, 0, 1, val);
          end else if (lane == 1 && bitn == 5) begin
            if ((col & 2) == 0) begin
              put_bit(col, 1, 5, val);
              put_bit(partner, 1, 5, val);
              seen1[g] = 1'b1;
            end else if (!seen1[g]) begin
              put_bit(col, 1, 5, val);
            end
          end else begin
            put_bit(col, lane, bitn, val);
          end
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
    fetch_split = 1'b0;
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
      integer s0, s1, off0, off1, c0, c1, e0, e1;
      s0 = 10;
      s1 = 10;
      center = 10;
      pin_even_en = 1'b0;
      pin_even = 16'h0;
      odd_clear = 16'h0;
      if (!$value$plusargs("ddr3_lane0=%d", s0))
        s0 = 10;
      if (!$value$plusargs("ddr3_lane1=%d", s1))
        s1 = 10;
      if (!$value$plusargs("ddr3_center=%d", center))
        center = 10;
      // Fetch image on the Dock: per-lane centers, not one center
      // and not the write-level edge. Place-fetch reads the step and
      // maps only codes 9 and 10 onto offset +1.
      c0 = center;
      c1 = center;
      if ($test$plusargs("ddr3_fetch_eye")) begin
        c0 = 11;
        c1 = 7;
        if ($value$plusargs("ddr3_edge0=%d", e0) &&
            $value$plusargs("ddr3_edge1=%d", e1)) begin
          // Same subtraction the bitstream uses. WLEVEL_BACKOFF is 1,
          // WLEVEL_BACKOFF1 is 3.
          c0 = e0 - 1;
          c1 = e1 - 3;
        end
      end
      if ($test$plusargs("ddr3_pd_eye")) begin
        // Display reference only. The measured codes are forced
        // below, and none of them is this center.
        c0 = 11;
        c1 = 7;
      end
      if ($test$plusargs("ddr3_place_fetch") &&
          !$test$plusargs("ddr3_fetch_eye") &&
          !$test$plusargs("ddr3_pd_eye")) begin
        off0 = (s0 == 9 || s0 == 10) ? 1 : (s0 - 10);
        off1 = (s1 == 9 || s1 == 10) ? 1 : (s1 - 10);
      end else if ($test$plusargs("ddr3_pd_eye")) begin
        // Measured Dock codes, all offset +1. Unmeasured codes are
        // not a Dock result.
        off0 = (s0 == 10 || s0 == 11) ? 1 : (s0 - 11);
        off1 = (s1 == 5 || s1 == 6 || s1 == 7) ? 1 : (s1 - 7);
      end else begin
        off0 = s0 - c0;
        off1 = s1 - c1;
      end
      eye_from_offset(off0, lane0_mode, lane0_sh);
      eye_from_offset(off1, lane1_mode, lane1_sh);
      if ($test$plusargs("ddr3_fetch_split"))
        fetch_split = 1'b1;
      if ($value$plusargs("ddr3_pin_even=%h", pin_even))
        pin_even_en = 1'b1;
      if (!$value$plusargs("ddr3_odd_clear=%h", odd_clear))
        odd_clear = 16'h0;
      $display("DDR3 model hold=%0d wloadn=%0d dm=%0d center0=%0d center1=%0d lane0=%0d(off %0d mode %0d sh %0d) lane1=%0d(off %0d mode %0d sh %0d) pin_even=%h odd_clear=%h corrupt=%0d late=%0d",
               hold_en, wloadn_en, dm_mode, c0, c1,
               s0, off0, lane0_mode, lane0_sh,
               s1, off1, lane1_mode, lane1_sh,
               pin_even_en ? pin_even : 16'h0, odd_clear,
               corrupt, late);
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
          end else if (fetch_split) begin
            apply_fetch_split(col, 0, din[7:0]);
            apply_fetch_split(col, 1, din[15:8]);
          end else if (pin_even_en) begin
            apply_masked(col, 0, din[7:0]);
            apply_masked(col, 1, din[15:8]);
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
