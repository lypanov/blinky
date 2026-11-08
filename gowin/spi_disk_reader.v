// SRAM-loaded reader for the Nano 4K flash disk.
//
// One 03h read at 0x200000. The first 20 bytes are the header: magic,
// version, build, length, checksum. The LED blinks only when magic and
// version match, the build equals EXPECT_BUILD, the length fits in
// 0x200000–0x3FFFFF, and the sum of the following little-endian words
// equals the checksum. Any other result stays dark. SPI mode 0.
// SPI_HALF is the SCLK high time and the SCLK low time, in `clk` cycles
// (54 → 250 kHz at 27 MHz).

`include "spi_disk_rates.vh"

module spi_disk_reader #(
  parameter [31:0] EXPECT_BUILD = `DISK_BUILD,
  parameter integer BLINK_HALF = `DISK_BLINK_HALF,
  parameter integer SPI_HALF = 54
) (
  input wire clk,
  input wire rst,
  output wire led,
  output reg spi_cs_n,
  output wire spi_clk,
  output wire spi_mosi,
  input wire spi_miso
);
  localparam [31:0] MAGIC = `DISK_MAGIC;
  localparam [31:0] VERSION = `DISK_VERSION;
  localparam [23:0] MAX_LEN = 24'h1FFFEC;

  localparam ST_GAP   = 3'd0;
  localparam ST_SETUP = 3'd1;
  localparam ST_KICK  = 3'd2;
  localparam ST_WAIT  = 3'd3;
  localparam ST_HALT  = 3'd4;

  localparam [15:0] GAP_CYCLES = 16'd16;
  localparam [2:0] CS_SETUP = 3'd4;

  reg [2:0] state;
  reg [23:0] pos;
  reg [15:0] gap;
  reg [2:0] setup;
  reg shift_start;
  reg [1:0] lane;
  reg [23:0] word_lo;
  reg [2:0] hword;
  reg in_payload;
  reg [23:0] left;
  reg [31:0] sum;
  reg [31:0] hdr_magic;
  reg [31:0] hdr_version;
  reg [31:0] hdr_build;
  reg [31:0] hdr_length;
  reg [31:0] hdr_sum;
  reg [31:0] got_sum;
  reg pass;
  reg [23:0] bdiv;
  reg led_q;

  wire shift_done;
  wire [7:0] shift_rx;
  wire [31:0] full_now = {shift_rx, word_lo};

  spi_shift #(.HALF(SPI_HALF)) u_shift (
    .clk   (clk),
    .rst   (rst),
    .start (shift_start),
    .tx    (tx_byte(pos)),
    .rx    (shift_rx),
    .done  (shift_done),
    .sclk  (spi_clk),
    .mosi  (spi_mosi),
    .miso  (spi_miso)
  );

  function [7:0] tx_byte;
    input [23:0] p;
    begin
      if (p == 24'd0)
        tx_byte = 8'h03;
      else if (p == 24'd1)
        tx_byte = 8'h20;
      else
        tx_byte = 8'h00;
    end
  endfunction

  function length_ok;
    input [31:0] n;
    begin
      length_ok = (n != 32'd0) && (n[1:0] == 2'b00) && (n[31:24] == 8'd0) && (n[23:0] <= MAX_LEN);
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
      pos <= 24'd0;
      gap <= GAP_CYCLES;
      setup <= 3'd0;
      lane <= 2'd0;
      word_lo <= 24'd0;
      hword <= 3'd0;
      in_payload <= 1'b0;
      left <= 24'd0;
      sum <= 32'd0;
      hdr_magic <= 32'd0;
      hdr_version <= 32'd0;
      hdr_build <= 32'd0;
      hdr_length <= 32'd0;
      hdr_sum <= 32'd0;
      got_sum <= 32'd0;
      pass <= 1'b0;
      spi_cs_n <= 1'b1;
    end else begin
      case (state)
        ST_GAP: begin
          spi_cs_n <= 1'b1;
          if (gap == 16'd0) begin
            pos <= 24'd0;
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
            if (pos < 24'd4) begin
              pos <= pos + 24'd1;
              state <= ST_KICK;
            end else if (!in_payload && lane != 2'd3) begin
              case (lane)
                2'd0: word_lo[7:0] <= shift_rx;
                2'd1: word_lo[15:8] <= shift_rx;
                default: word_lo[23:16] <= shift_rx;
              endcase
              lane <= lane + 2'd1;
              pos <= pos + 24'd1;
              state <= ST_KICK;
            end else if (!in_payload) begin
              lane <= 2'd0;
              pos <= pos + 24'd1;
              case (hword)
                3'd0: begin
                  hdr_magic <= full_now;
                  hword <= 3'd1;
                  state <= ST_KICK;
                end
                3'd1: begin
                  hdr_version <= full_now;
                  hword <= 3'd2;
                  state <= ST_KICK;
                end
                3'd2: begin
                  hdr_build <= full_now;
                  hword <= 3'd3;
                  state <= ST_KICK;
                end
                3'd3: begin
                  hdr_length <= full_now;
                  hword <= 3'd4;
                  state <= ST_KICK;
                end
                default: begin
                  hdr_sum <= full_now;
                  if (hdr_magic == MAGIC && hdr_version == VERSION &&
                      hdr_build == EXPECT_BUILD && length_ok(hdr_length)) begin
                    in_payload <= 1'b1;
                    left <= hdr_length[23:0];
                    sum <= 32'd0;
                    state <= ST_KICK;
                  end else begin
                    spi_cs_n <= 1'b1;
                    state <= ST_HALT;
                  end
                end
              endcase
            end else if (lane != 2'd3) begin
              case (lane)
                2'd0: word_lo[7:0] <= shift_rx;
                2'd1: word_lo[15:8] <= shift_rx;
                default: word_lo[23:16] <= shift_rx;
              endcase
              lane <= lane + 2'd1;
              left <= left - 24'd1;
              pos <= pos + 24'd1;
              state <= ST_KICK;
            end else begin
              got_sum <= sum + full_now;
              sum <= sum + full_now;
              lane <= 2'd0;
              if (left == 24'd1) begin
                if ((sum + full_now) == hdr_sum)
                  pass <= 1'b1;
                spi_cs_n <= 1'b1;
                state <= ST_HALT;
              end else begin
                left <= left - 24'd1;
                pos <= pos + 24'd1;
                state <= ST_KICK;
              end
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
