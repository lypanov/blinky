// Forces the LED pin off while a button is held or a UART press byte
// is latched. cpu_led keeps toggling. The pin is cpu_led when neither
// source says pressed, so a release shows the phase the register is
// already in. Nothing here stalls the CPU.
//
// btn_n is active-low. Two flops synchronise it. A board with no
// button ties it high.
//
// UART is 8N1 at 115200. CLKS_PER_BIT is clk/115200, rounded.
// The Nano 4K gate clock is cpu_clk, 13.5 MHz, so CLKS_PER_BIT is 117.
// The Dock gate clock is cpu_clk, 24.1875 MHz, so CLKS_PER_BIT is 210.
// Press: 0x01, ASCII '1' (0x31), or space (0x20).
// Release: 0x00 or ASCII '0' (0x30). Any other byte leaves the latch.
// ENABLE_UART 0 drops the receiver. The latch stays clear.

module button_gate #(
  parameter integer CLKS_PER_BIT = 117,
  parameter integer ENABLE_UART = 1
) (
  input  wire clk,
  input  wire resetn,
  input  wire cpu_led,
  input  wire btn_n,
  input  wire uart_rx,
  output wire led,
  output wire pressed
);
  reg btn0 = 1'b1;
  reg btn1 = 1'b1;
  reg uart_latch = 1'b0;

  always @(posedge clk) begin
    if (!resetn) begin
      btn0 <= 1'b1;
      btn1 <= 1'b1;
    end else begin
      btn0 <= btn_n;
      btn1 <= btn0;
    end
  end

  generate
    if (ENABLE_UART != 0) begin : g_uart
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
      wire rx_fall = rx1 & ~rx0;

      always @(posedge clk) begin
        if (!resetn) begin
          rx0 <= 1'b1;
          rx1 <= 1'b1;
          state <= S_IDLE;
          cnt <= 9'd0;
          bitn <= 3'd0;
          sh <= 8'd0;
          uart_latch <= 1'b0;
        end else begin
          rx0 <= uart_rx;
          rx1 <= rx0;
          case (state)
            S_IDLE: begin
              cnt <= 9'd0;
              if (rx_fall) state <= S_START;
            end
            S_START: begin
              if (cnt == HALF_LAST) begin
                cnt <= 9'd0;
                bitn <= 3'd0;
                // A high here is a glitch, not a start bit.
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
                // Stop bit must be high. LSB was shifted in first.
                if (rx0 == 1'b1) begin
                  if (sh == 8'h01 || sh == 8'h31 || sh == 8'h20)
                    uart_latch <= 1'b1;
                  else if (sh == 8'h00 || sh == 8'h30)
                    uart_latch <= 1'b0;
                end
              end else cnt <= cnt + 9'd1;
            end
          endcase
        end
      end
    end else begin : g_no_uart
      wire unused_rx = uart_rx;
      always @(posedge clk) begin
        if (!resetn) uart_latch <= 1'b0;
        else uart_latch <= 1'b0;
      end
    end
  endgenerate

  assign pressed = uart_latch | ~btn1;
  // Active-high CPU LED. Pressed forces the pin off.
  assign led = cpu_led & ~pressed;
endmodule
