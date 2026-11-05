// 64-word round trip on the Dock DDR3 command port.
//
// The behavioural model presents dout on the same clock as data_ready
// and then holds it. The PHY's dq_in word can move a clock later than
// data_ready, which the model does not do. Each read keeps the word on
// data_ready and the two following clocks. The first word picks the
// edge that matches; every later word has to match that same edge.
//
// After every command the controller drops busy at tRC. A 1 Gbit DDR3
// needs tRFC (110 ns) after a refresh, so the next command waits 16
// controller clocks (165 ns at 96.75 MHz) on top of busy.

module ddr3_port_test #(
  parameter integer WORDS = 64,
  parameter [7:0] GAP = 8'd16
) (
  input              clk,
  input              resetn,
  input              calib,
  output reg         rd,
  output reg         wr,
  output reg         refresh,
  output reg  [25:0] addr,
  output reg  [15:0] din,
  input       [15:0] dout,
  input              data_ready,
  input              busy,
  output reg         passed,
  output reg         failed,
  output reg         done,
  output reg  [1:0]  edge_sel,
  output reg         noready,
  output reg  [15:0] samp0,
  output reg  [15:0] samp1,
  output reg  [15:0] samp2
);
  localparam [3:0] ST_WAIT  = 4'd0;
  localparam [3:0] ST_WCMD  = 4'd1;
  localparam [3:0] ST_WBUSY = 4'd2;
  localparam [3:0] ST_REF   = 4'd3;
  localparam [3:0] ST_RBUSY = 4'd4;
  localparam [3:0] ST_GAP   = 4'd5;
  localparam [3:0] ST_RCMD  = 4'd6;
  localparam [3:0] ST_READ  = 4'd7;
  localparam [3:0] ST_S1    = 4'd8;
  localparam [3:0] ST_S2    = 4'd9;
  localparam [3:0] ST_NEXT  = 4'd10;
  localparam [3:0] ST_DONE  = 4'd11;

  reg [3:0]  state;
  reg        saw_busy;
  reg        reading;
  reg        locked;
  reg [1:0]  use_edge;
  reg [15:0] s0;
  reg [15:0] s1;
  reg [7:0]  gap;
  reg        gap_to_read;

  wire [15:0] pattern = addr[15:0] ^ 16'hA5A5;

  task automatic fail_at;
    input [15:0] a;
    input [15:0] b;
    input [15:0] c;
    begin
      samp0 <= a;
      samp1 <= b;
      samp2 <= c;
      failed <= 1'b1;
      done <= 1'b1;
      state <= ST_DONE;
    end
  endtask

  always @(posedge clk or negedge resetn) begin
    if (!resetn) begin
      state <= ST_WAIT;
      rd <= 1'b0;
      wr <= 1'b0;
      refresh <= 1'b0;
      addr <= 26'd0;
      din <= 16'd0;
      passed <= 1'b0;
      failed <= 1'b0;
      done <= 1'b0;
      edge_sel <= 2'd0;
      noready <= 1'b0;
      samp0 <= 16'd0;
      samp1 <= 16'd0;
      samp2 <= 16'd0;
      saw_busy <= 1'b0;
      reading <= 1'b0;
      locked <= 1'b0;
      use_edge <= 2'd0;
      s0 <= 16'd0;
      s1 <= 16'd0;
      gap <= 8'd0;
      gap_to_read <= 1'b0;
    end else begin
      rd <= 1'b0;
      wr <= 1'b0;
      refresh <= 1'b0;
      case (state)
        ST_WAIT: begin
          if (calib && !busy) begin
            addr <= 26'd0;
            reading <= 1'b0;
            locked <= 1'b0;
            state <= ST_WCMD;
          end
        end

        ST_WCMD: begin
          wr <= 1'b1;
          din <= pattern;
          saw_busy <= 1'b0;
          state <= ST_WBUSY;
        end

        ST_RCMD: begin
          rd <= 1'b1;
          saw_busy <= 1'b0;
          state <= ST_READ;
        end

        ST_WBUSY: begin
          if (busy)
            saw_busy <= 1'b1;
          if (saw_busy && !busy) begin
            gap <= GAP;
            gap_to_read <= 1'b0;
            state <= ST_GAP;
          end
        end

        ST_REF: begin
          refresh <= 1'b1;
          saw_busy <= 1'b0;
          state <= ST_RBUSY;
        end

        ST_RBUSY: begin
          if (busy)
            saw_busy <= 1'b1;
          if (saw_busy && !busy) begin
            gap <= GAP;
            state <= ST_GAP;
          end
        end

        ST_GAP: begin
          if (gap == 8'd0) begin
            if (!reading && !gap_to_read) begin
              gap_to_read <= 1'b1;
              state <= ST_REF;
            end else if (!reading) begin
              gap_to_read <= 1'b0;
              if (addr == WORDS - 1) begin
                addr <= 26'd0;
                reading <= 1'b1;
                state <= ST_RCMD;
              end else begin
                addr <= addr + 26'd1;
                state <= ST_WCMD;
              end
            end else if (!gap_to_read) begin
              gap_to_read <= 1'b1;
              state <= ST_REF;
            end else begin
              gap_to_read <= 1'b0;
              if (addr == WORDS - 1) begin
                passed <= 1'b1;
                edge_sel <= use_edge;
                done <= 1'b1;
                state <= ST_DONE;
              end else begin
                addr <= addr + 26'd1;
                state <= ST_RCMD;
              end
            end
          end else
            gap <= gap - 8'd1;
        end

        ST_READ: begin
          if (busy)
            saw_busy <= 1'b1;
          if (data_ready) begin
            s0 <= dout;
            state <= ST_S1;
          end else if (saw_busy && !busy) begin
            noready <= 1'b1;
            fail_at(16'h0000, 16'h0000, 16'h0000);
          end
        end

        ST_S1: begin
          s1 <= dout;
          state <= ST_S2;
        end

        ST_S2: begin
          if (!locked) begin
            if (s0 == pattern) begin
              locked <= 1'b1;
              use_edge <= 2'd0;
              state <= ST_NEXT;
            end else if (s1 == pattern) begin
              locked <= 1'b1;
              use_edge <= 2'd1;
              state <= ST_NEXT;
            end else if (dout == pattern) begin
              locked <= 1'b1;
              use_edge <= 2'd2;
              state <= ST_NEXT;
            end else
              fail_at(s0, s1, dout);
          end else if ((use_edge == 2'd0 && s0 != pattern) ||
                       (use_edge == 2'd1 && s1 != pattern) ||
                       (use_edge == 2'd2 && dout != pattern)) begin
            fail_at(s0, s1, dout);
          end else
            state <= ST_NEXT;
        end

        ST_NEXT: begin
          gap <= GAP;
          gap_to_read <= 1'b0;
          state <= ST_GAP;
        end

        ST_DONE: begin
        end

        default: state <= ST_WAIT;
      endcase
    end
  end
endmodule

// 8N1 transmitter. CLKS_PER_BIT is pclk/baud, rounded.
module ddr3_uart_tx #(
  parameter integer CLKS_PER_BIT = 840
) (
  input            clk,
  input            resetn,
  input      [7:0] data,
  input            we,
  output reg       tx,
  output           busy
);
  reg [9:0] sh;
  reg [15:0] div;
  reg [3:0] bits;
  reg       running;
  assign busy = running;

  always @(posedge clk or negedge resetn) begin
    if (!resetn) begin
      tx <= 1'b1;
      sh <= 10'h3ff;
      div <= 16'd0;
      bits <= 4'd0;
      running <= 1'b0;
    end else if (!running) begin
      tx <= 1'b1;
      if (we) begin
        sh <= {1'b1, data, 1'b0};
        bits <= 4'd10;
        div <= CLKS_PER_BIT[15:0] - 16'd1;
        running <= 1'b1;
      end
    end else if (div != 0) begin
      div <= div - 16'd1;
    end else begin
      tx <= sh[0];
      sh <= {1'b1, sh[9:1]};
      div <= CLKS_PER_BIT[15:0] - 16'd1;
      bits <= bits - 4'd1;
      if (bits == 4'd1)
        running <= 1'b0;
    end
  end
endmodule
