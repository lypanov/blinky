// Tang Nano 4K wrapper for the SPI-flash pathfinder.
// spi_flash_cfg.vh selects the image (JEDEC, writer, reader, negative).
// Pin 45 goes through PLLVR bypass so the blink divider sees 27 MHz.
// Reset pin 15 is pull-down, active-high: unpressed is run.
// WP# and HOLD# are driven high so the NOR stays in ordinary SPI.

`include "spi_flash_cfg.vh"

module spi_flash_top (
  input wire clock,
  input wire reset,
  output wire io_led,
  output wire spi_cs_n,
  output wire spi_clk,
  output wire spi_mosi,
  input wire spi_miso,
  output wire spi_wp,
  output wire spi_hold
);
  wire clk_sys;
  reg [7:0] por = 8'hff;
  wire rst;

  Gowin_PLLVR u_pll (
    .clkout (clk_sys),
    .clkin  (clock)
  );

  always @(posedge clk_sys) begin
    if (por != 8'h00)
      por <= por - 8'h01;
  end
  assign rst = (por != 8'h00) | reset;

  spi_flash_pathfinder #(
    .MODE       (`SPI_FLASH_MODE),
    .BUILD      (`SPI_FLASH_BUILD),
    .BLINK_HALF (`SPI_FLASH_HALF),
    .SPI_HALF   (54)
  ) u_pf (
    .clk       (clk_sys),
    .rst       (rst),
    .led       (io_led),
    .spi_cs_n  (spi_cs_n),
    .spi_clk   (spi_clk),
    .spi_mosi  (spi_mosi),
    .spi_miso  (spi_miso)
  );

  assign spi_wp = 1'b1;
  assign spi_hold = 1'b1;
endmodule
