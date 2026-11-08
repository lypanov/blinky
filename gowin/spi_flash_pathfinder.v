// Standalone SPI NOR pathfinder. No CPU.
//
// MODE 0: 9Fh JEDEC ID. Blink if the part is a Puya P25Q32 (85 60 16).
// MODE 1: that ID check, then 06h / 20h erase / 02h page program / 03h
//         read-back of the 256-byte page at SPI_PAGE_ADDR. Blink on match.
// MODE 2: 03h read of that page. Blink only if every byte matches BUILD.
//
// Commands are only 9Fh, 05h, 06h, 20h, 02h, and 03h. A wrong ID never
// reaches the erase. The LED is active-high and stays low on any failure.
// SPI mode 0, MSB first. SPI_HALF is the SCLK high time and the SCLK low
// time, in `clk` cycles (54 → 250 kHz at 27 MHz).

module spi_shift #(
  parameter HALF = 54
) (
  input wire clk,
  input wire rst,
  input wire start,
  input wire [7:0] tx,
  output reg [7:0] rx,
  output reg done,
  output reg sclk,
  output reg mosi,
  input wire miso
);
  reg running;
  reg hi;
  reg [15:0] div;
  reg [2:0] bitn;
  reg [7:0] txsh;
  reg [7:0] rxsh;

  always @(posedge clk) begin
    done <= 1'b0;
    if (rst) begin
      running <= 1'b0;
      hi <= 1'b0;
      div <= 16'd0;
      bitn <= 3'd0;
      txsh <= 8'd0;
      rxsh <= 8'd0;
      rx <= 8'd0;
      sclk <= 1'b0;
      mosi <= 1'b0;
    end else if (start && !running) begin
      running <= 1'b1;
      hi <= 1'b0;
      div <= 16'd0;
      bitn <= 3'd0;
      txsh <= {tx[6:0], 1'b0};
      rxsh <= 8'd0;
      sclk <= 1'b0;
      mosi <= tx[7];
    end else if (running) begin
      if (div != HALF - 1) begin
        div <= div + 16'd1;
      end else begin
        div <= 16'd0;
        if (!hi) begin
          sclk <= 1'b1;
          hi <= 1'b1;
          rxsh <= {rxsh[6:0], miso};
        end else begin
          sclk <= 1'b0;
          hi <= 1'b0;
          if (bitn == 3'd7) begin
            running <= 1'b0;
            done <= 1'b1;
            rx <= rxsh;
          end else begin
            bitn <= bitn + 3'd1;
            mosi <= txsh[7];
            txsh <= {txsh[6:0], 1'b0};
          end
        end
      end
    end
  end
endmodule

module spi_flash_pathfinder #(
  parameter MODE = 0,
  parameter [7:0] BUILD = 8'h7B,
  parameter BLINK_HALF = 9000000,
  parameter SPI_HALF = 54
) (
  input wire clk,
  input wire rst,
  output wire led,
  output reg spi_cs_n,
  output wire spi_clk,
  output wire spi_mosi,
  input wire spi_miso
);
  localparam STEP_JEDEC = 4'd0;
  localparam STEP_WREN1 = 4'd1;
  localparam STEP_ERASE = 4'd2;
  localparam STEP_STAT1 = 4'd3;
  localparam STEP_WREN2 = 4'd4;
  localparam STEP_PROG  = 4'd5;
  localparam STEP_STAT2 = 4'd6;
  localparam STEP_READ  = 4'd7;
  localparam STEP_HALT  = 4'd8;

  localparam ST_GAP   = 3'd0;
  localparam ST_SETUP = 3'd1;
  localparam ST_KICK  = 3'd2;
  localparam ST_WAIT  = 3'd3;
  localparam ST_HALT  = 3'd4;

  localparam [7:0] ID0 = 8'h85;
  localparam [7:0] ID1 = 8'h60;
  localparam [7:0] ID2 = 8'h16;
  localparam [15:0] ERASE_POLLS = 16'd40000;
  localparam [15:0] PROG_POLLS = 16'd4000;
  localparam [15:0] GAP_CYCLES = 16'd16;
  localparam [2:0] CS_SETUP = 3'd4;

  reg [2:0] state;
  reg [3:0] step;
  reg [9:0] idx;
  reg [15:0] gap;
  reg [2:0] setup;
  reg [15:0] polls;
  reg shift_start;
  reg [7:0] id0;
  reg [7:0] id1;
  reg [7:0] id2;
  reg wip;
  reg mismatch;
  reg pass;
  reg [23:0] bdiv;
  reg led_q;

  wire shift_done;
  wire [7:0] shift_rx;

  spi_shift #(.HALF(SPI_HALF)) u_shift (
    .clk   (clk),
    .rst   (rst),
    .start (shift_start),
    .tx    (tx_byte(step, idx)),
    .rx    (shift_rx),
    .done  (shift_done),
    .sclk  (spi_clk),
    .mosi  (spi_mosi),
    .miso  (spi_miso)
  );

  function [7:0] page_byte;
    input [7:0] i;
    input [7:0] build;
    begin
      if (i == 8'd0)
        page_byte = 8'hA5;
      else if (i == 8'd1)
        page_byte = 8'h5A;
      else if (i == 8'd2)
        page_byte = build;
      else
        page_byte = i ^ build;
    end
  endfunction

  function [7:0] read_expect;
    input [9:0] i;
    reg [9:0] d;
    begin
      d = i - 10'd4;
      read_expect = page_byte(d[7:0], BUILD);
    end
  endfunction

  function [9:0] step_nbytes;
    input [3:0] s;
    begin
      case (s)
        STEP_JEDEC: step_nbytes = 10'd4;
        STEP_WREN1, STEP_WREN2: step_nbytes = 10'd1;
        STEP_ERASE: step_nbytes = 10'd4;
        STEP_STAT1, STEP_STAT2: step_nbytes = 10'd2;
        STEP_PROG, STEP_READ: step_nbytes = 10'd260;
        default: step_nbytes = 10'd1;
      endcase
    end
  endfunction

  function [7:0] tx_byte;
    input [3:0] s;
    input [9:0] i;
    reg [8:0] data_i;
    begin
      data_i = i[8:0] - 9'd4;
      if (i == 10'd0) begin
        case (s)
          STEP_JEDEC: tx_byte = 8'h9F;
          STEP_WREN1, STEP_WREN2: tx_byte = 8'h06;
          STEP_ERASE: tx_byte = 8'h20;
          STEP_STAT1, STEP_STAT2: tx_byte = 8'h05;
          STEP_PROG: tx_byte = 8'h02;
          STEP_READ: tx_byte = 8'h03;
          default: tx_byte = 8'h00;
        endcase
      end else if ((s == STEP_ERASE || s == STEP_PROG || s == STEP_READ) && i == 10'd1)
        tx_byte = 8'h3F;
      else if ((s == STEP_ERASE || s == STEP_PROG || s == STEP_READ) && i == 10'd2)
        tx_byte = 8'hF0;
      else if ((s == STEP_ERASE || s == STEP_PROG || s == STEP_READ) && i == 10'd3)
        tx_byte = 8'h00;
      else if (s == STEP_PROG && i >= 10'd4)
        tx_byte = page_byte(data_i[7:0], BUILD);
      else
        tx_byte = 8'h00;
    end
  endfunction

  function id_match;
    input [7:0] a;
    input [7:0] b;
    input [7:0] c;
    begin
      id_match = (a == ID0) && (b == ID1) && (c == ID2);
    end
  endfunction

  assign led = led_q;

  always @(posedge clk) begin
    if (rst || !pass) begin
      bdiv <= 24'd0;
      led_q <= 1'b0;
    end else if (bdiv == BLINK_HALF - 1) begin
      bdiv <= 24'd0;
      led_q <= ~led_q;
    end else begin
      bdiv <= bdiv + 24'd1;
    end
  end

  always @(posedge clk) begin
    shift_start <= 1'b0;
    if (rst) begin
      state <= ST_GAP;
      step <= (MODE == 2) ? STEP_READ : STEP_JEDEC;
      idx <= 10'd0;
      gap <= GAP_CYCLES;
      setup <= 3'd0;
      polls <= 16'd0;
      spi_cs_n <= 1'b1;
      id0 <= 8'd0;
      id1 <= 8'd0;
      id2 <= 8'd0;
      wip <= 1'b1;
      mismatch <= 1'b0;
      pass <= 1'b0;
    end else begin
      case (state)
        ST_GAP: begin
          spi_cs_n <= 1'b1;
          if (step == STEP_HALT) begin
            state <= ST_HALT;
          end else if (gap == 16'd0) begin
            idx <= 10'd0;
            setup <= CS_SETUP;
            spi_cs_n <= 1'b0;
            state <= ST_SETUP;
          end else begin
            gap <= gap - 16'd1;
          end
        end
        ST_SETUP: begin
          spi_cs_n <= 1'b0;
          if (setup == 3'd0)
            state <= ST_KICK;
          else
            setup <= setup - 3'd1;
        end
        ST_KICK: begin
          shift_start <= 1'b1;
          state <= ST_WAIT;
        end
        ST_WAIT: begin
          if (shift_done) begin
            if (step == STEP_JEDEC && idx == 10'd1)
              id0 <= shift_rx;
            if (step == STEP_JEDEC && idx == 10'd2)
              id1 <= shift_rx;
            if (step == STEP_JEDEC && idx == 10'd3)
              id2 <= shift_rx;
            if ((step == STEP_STAT1 || step == STEP_STAT2) && idx == 10'd1)
              wip <= shift_rx[0];
            if (step == STEP_READ && idx >= 10'd4) begin
              if (shift_rx != read_expect(idx))
                mismatch <= 1'b1;
            end
            if (idx + 10'd1 == step_nbytes(step)) begin
              state <= ST_GAP;
              gap <= GAP_CYCLES;
              spi_cs_n <= 1'b1;
              case (step)
                STEP_JEDEC: begin
                  // id0 and id1 landed on earlier bytes. This byte is id2.
                  if (id_match(id0, id1, shift_rx)) begin
                    if (MODE == 0)
                      pass <= 1'b1;
                    step <= (MODE == 0) ? STEP_HALT : STEP_WREN1;
                  end else begin
                    step <= STEP_HALT;
                  end
                end
                STEP_WREN1: step <= STEP_ERASE;
                STEP_ERASE: begin
                  polls <= 16'd0;
                  step <= STEP_STAT1;
                end
                STEP_STAT1: begin
                  if (!shift_rx[0]) begin
                    step <= STEP_WREN2;
                  end else if (polls == ERASE_POLLS) begin
                    step <= STEP_HALT;
                  end else begin
                    polls <= polls + 16'd1;
                    step <= STEP_STAT1;
                  end
                end
                STEP_WREN2: step <= STEP_PROG;
                STEP_PROG: begin
                  polls <= 16'd0;
                  step <= STEP_STAT2;
                end
                STEP_STAT2: begin
                  if (!shift_rx[0]) begin
                    mismatch <= 1'b0;
                    step <= STEP_READ;
                  end else if (polls == PROG_POLLS) begin
                    step <= STEP_HALT;
                  end else begin
                    polls <= polls + 16'd1;
                    step <= STEP_STAT2;
                  end
                end
                STEP_READ: begin
                  // `mismatch` does not yet include this byte.
                  if (shift_rx != read_expect(idx) || mismatch)
                    pass <= 1'b0;
                  else
                    pass <= 1'b1;
                  step <= STEP_HALT;
                end
                default: step <= STEP_HALT;
              endcase
            end else begin
              idx <= idx + 10'd1;
              state <= ST_KICK;
            end
          end
        end
        ST_HALT: begin
          spi_cs_n <= 1'b1;
        end
        default: state <= ST_HALT;
      endcase
    end
  end
endmodule
