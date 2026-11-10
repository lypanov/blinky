// CPUSimTop plus the SPI disk model. The model is clocked by the bridge
// clock. The CPU and its shifter run at half that rate, inside CPUSimTop.
module disk_boot_top (
  input  wire clock,
  input  wire reset,
  output wire led,
  output wire halted,
  output wire [31:0] pc,
  output wire [39:0] mask,
  output wire [31:0] r5,
  output wire [31:0] r9,
  output wire mem_write,
  output wire [31:0] mem_addr,
  output wire screen_we
);
  wire cs_n;
  wire sclk;
  wire mosi;
  wire miso;

  CPUSimTop cpu (
    .clock(clock),
    .reset(reset),
    .io_led(led),
    .io_halted(halted),
    .io_pc(pc),
    .io_mask(mask),
    .io_r5(r5),
    .io_r9(r9),
    .io_spiCsN(cs_n),
    .io_spiClk(sclk),
    .io_spiMosi(mosi),
    .io_spiMiso(miso),
    .io_memWrite(mem_write),
    .io_memAddr(mem_addr),
    .io_screenWe(screen_we),
    .io_diskValid(1'b0),
    .io_diskWord(32'd0),
    .io_diskTake(),
    .io_cpuClk()
  );

  spi_disk_model flash (
    .clk(clock),
    .cs_n(cs_n),
    .sclk(sclk),
    .mosi(mosi),
    .miso(miso)
  );
endmodule
