// Behavioural stand-in for ddr3_controller's command port.
//
// The PHY (OSER8/DQS/DLL) is not simulated. What is simulated is the
// post-calibration command timing of that controller, DDR3-800:
//
//   * rd/wr/refresh are one-cycle pulses, sampled when busy is low.
//   * addr is a 16-bit-word address. din/dout are that one word.
//   * A read presents dout with data_ready nine clocks after the pulse,
//     and drops busy on the tenth clock. A write or a refresh drops
//     busy on the sixth clock. Those are the controller's `cycle`
//     compares (data_ready when cycle==8, busy cleared when cycle==9
//     for a read and when cycle==5 for a write or a refresh).
//   * calib rises after INIT_CYCLES and stays high. Real write leveling
//     is milliseconds; the blink period is measured after it.
//
// +ddr3_corrupt makes every read return 0. The prologue must then keep
// the LED dark. The data_ready timing does not change.
//
// The array is 4096 words (8 KB). A word address above that is a fault
// and reads as 0, which fails the pattern compare.

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

  reg [15:0] mem [0:WORDS-1];
  reg [15:0] init_cnt;
  reg [15:0] hold;
  reg [4:0]  cycle;
  reg [1:0]  op;       // 0 idle, 1 read, 2 write, 3 refresh
  reg        corrupt;
  reg        late;
  reg        dout_pend;
  integer    i;

  initial begin
    corrupt = 1'b0;
    late = 1'b0;
    dout_pend = 1'b0;
    dout = 16'd0;
    data_ready = 1'b0;
    busy = 1'b0;
    calib = 1'b0;
    op = 2'd0;
    cycle = 5'd0;
    init_cnt = 16'd0;
    for (i = 0; i < WORDS; i = i + 1)
      mem[i] = 16'd0;
    if ($test$plusargs("ddr3_corrupt"))
      corrupt = 1'b1;
    if ($test$plusargs("ddr3_late"))
      late = 1'b1;
  end

  wire in_range = addr[25:12] == 14'd0;
  wire [11:0] idx = addr[11:0];

  always @(posedge clk) begin
    data_ready <= 1'b0;
    if (!rst_n) begin
      busy <= 1'b0;
      calib <= 1'b0;
      op <= 2'd0;
      cycle <= 5'd0;
      init_cnt <= 16'd0;
      dout <= 16'd0;
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
            hold <= mem[idx];
        end else if (wr) begin
          op <= 2'd2;
          if (!in_range)
            $display("DDR3_RANGE_FAULT write addr=%h", addr);
          else
            mem[idx] <= din;
        end else begin
          op <= 2'd3;
        end
      end
    end
  end
endmodule
