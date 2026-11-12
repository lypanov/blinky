// Little-endian words from an 8N1 UART. The Dock bootstrap loads these
// the way the 4K bootstrap loads NOR words. clk is cpu_clk.
// The Dock uses CLKS_PER_BIT 210 (24.1875 MHz / 115200).
// A word is four bytes, first byte in bits [7:0]. Eight words of
// buffering cover a DDR3 store between loads. take drops the oldest.

module uart_word_rx #(
  parameter integer CLKS_PER_BIT = 210,
  // Clocks after reset during which a start bit is ignored. 0
  // accepts a byte immediately. The Dock image passes 2^18.
  parameter integer QUIET_CLKS = 0
) (
  input  wire        clk,
  input  wire        resetn,
  input  wire        rx,
  output wire        valid,
  output wire [31:0] word,
  input  wire        take
);
  localparam integer HALF = CLKS_PER_BIT / 2;
  // verilator lint_off WIDTHTRUNC
  localparam [8:0] BIT_LAST = CLKS_PER_BIT - 1;
  localparam [8:0] HALF_LAST = HALF - 1;
  // verilator lint_on WIDTHTRUNC
  localparam [1:0] S_IDLE = 2'd0;
  localparam [1:0] S_START = 2'd1;
  localparam [1:0] S_DATA = 2'd2;
  localparam [1:0] S_STOP = 2'd3;

  reg rx0 = 1'b1;
  reg rx1 = 1'b1;
  reg [1:0] state = S_IDLE;
  reg [8:0] cnt = 9'd0;
  reg [2:0] bitn = 3'd0;
  reg [7:0] sh = 8'd0;
  reg [31:0] pack = 32'd0;
  reg [1:0] got = 2'd0;
  wire rx_fall = rx1 & ~rx0;

  reg [31:0] fifo0 = 32'd0;
  reg [31:0] fifo1 = 32'd0;
  reg [31:0] fifo2 = 32'd0;
  reg [31:0] fifo3 = 32'd0;
  reg [31:0] fifo4 = 32'd0;
  reg [31:0] fifo5 = 32'd0;
  reg [31:0] fifo6 = 32'd0;
  reg [31:0] fifo7 = 32'd0;
  reg [2:0] wr = 3'd0;
  reg [2:0] rd = 3'd0;
  reg [3:0] nwords = 4'd0;
  // Wide enough for the Dock's 2^18 quiet window. A 0 parameter
  // never counts, so the sim accepts the first start bit.
  reg [18:0] quiet = 19'd0;
  wire quiet_done = (QUIET_CLKS == 0) || (quiet >= QUIET_CLKS[18:0]);

  assign valid = nwords != 4'd0;
  assign word = (rd == 3'd0) ? fifo0 :
                (rd == 3'd1) ? fifo1 :
                (rd == 3'd2) ? fifo2 :
                (rd == 3'd3) ? fifo3 :
                (rd == 3'd4) ? fifo4 :
                (rd == 3'd5) ? fifo5 :
                (rd == 3'd6) ? fifo6 : fifo7;

  // Same-cycle push decision. Not a flop.
  reg do_push;
  reg [31:0] push_word;

  always @(posedge clk) begin
    if (!resetn) begin
      rx0 <= 1'b1;
      rx1 <= 1'b1;
      state <= S_IDLE;
      cnt <= 9'd0;
      bitn <= 3'd0;
      sh <= 8'd0;
      pack <= 32'd0;
      got <= 2'd0;
      wr <= 3'd0;
      rd <= 3'd0;
      nwords <= 4'd0;
      quiet <= 19'd0;
      do_push = 1'b0;
      push_word = 32'd0;
    end else begin
      rx0 <= rx;
      rx1 <= rx0;
      do_push = 1'b0;
      push_word = 32'd0;
      if (!quiet_done)
        quiet <= quiet + 19'd1;
      case (state)
        S_IDLE: begin
          cnt <= 9'd0;
          if (rx_fall && quiet_done) state <= S_START;
        end
        S_START: begin
          if (cnt == HALF_LAST) begin
            cnt <= 9'd0;
            bitn <= 3'd0;
            if (rx0 == 1'b0) state <= S_DATA;
            else state <= S_IDLE;
          end else cnt <= cnt + 9'd1;
        end
        S_DATA: begin
          if (cnt == BIT_LAST) begin
            cnt <= 9'd0;
            sh <= {rx0, sh[7:1]};
            if (bitn == 3'd7) state <= S_STOP;
            else bitn <= bitn + 3'd1;
          end else cnt <= cnt + 9'd1;
        end
        default: begin
          if (cnt == BIT_LAST) begin
            cnt <= 9'd0;
            state <= S_IDLE;
            // Stop bit must be high. sh already holds the byte.
            if (rx0 == 1'b1) begin
              if (got == 2'd3) begin
                got <= 2'd0;
                do_push = 1'b1;
                push_word = {sh, pack[31:8]};
                pack <= 32'd0;
              end else begin
                got <= got + 2'd1;
                pack <= {sh, pack[31:8]};
              end
            end
          end else cnt <= cnt + 9'd1;
        end
      endcase

      if (do_push && nwords != 4'd8) begin
        case (wr)
          3'd0: fifo0 <= push_word;
          3'd1: fifo1 <= push_word;
          3'd2: fifo2 <= push_word;
          3'd3: fifo3 <= push_word;
          3'd4: fifo4 <= push_word;
          3'd5: fifo5 <= push_word;
          3'd6: fifo6 <= push_word;
          default: fifo7 <= push_word;
        endcase
        wr <= wr + 3'd1;
      end
      // Both in one cycle: the new word replaces the one just taken.
      if (do_push && nwords != 4'd8 && take && nwords != 4'd0)
        nwords <= nwords;
      else if (take && nwords != 4'd0)
        nwords <= nwords - 4'd1;
      else if (do_push && nwords != 4'd8)
        nwords <= nwords + 4'd1;
      if (take && nwords != 4'd0)
        rd <= rd + 3'd1;
    end
  end
endmodule
