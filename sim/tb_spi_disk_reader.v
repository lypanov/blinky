// Functional sim of the flash-disk reader. SPI and blink dividers are
// shortened. The FPGA images keep the published half-period. The NOR
// model is loaded with disk.bin, the same file the host writes at 0x200000.
`timescale 1ns/1ps

module tb_spi_disk_reader;
  localparam integer BLINK = 20;
  localparam integer SPIH = 1;
  localparam [31:0] BUILD_YES = 32'h000000D1;
  localparam [31:0] BUILD_NO = 32'h000000D2;
  localparam [23:0] BASE = 24'h200000;

  reg clk;
  initial clk = 1'b0;
  always #5 clk = ~clk;

  reg done_ok = 1'b0;
  reg done_neg = 1'b0;
  reg done_bad = 1'b0;
  reg done_blank = 1'b0;

  task fail;
    input [511:0] msg;
    begin
      $display("SPI_DISK FAIL %0s", msg);
      $fatal(1);
    end
  endtask

  reg rst_ok;
  wire led_ok, cs_ok, sck_ok, mo_ok, mi_ok;
  spi_disk_model #(.LOAD(1), .FILE("sim/out/disk.bin")) flash_ok (
    .clk (clk), .cs_n (cs_ok), .sclk (sck_ok), .mosi (mo_ok), .miso (mi_ok)
  );
  spi_disk_reader #(.EXPECT_BUILD(BUILD_YES), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_ok (
    .clk (clk), .rst (rst_ok), .led (led_ok),
    .spi_cs_n (cs_ok), .spi_clk (sck_ok), .spi_mosi (mo_ok), .spi_miso (mi_ok)
  );

  reg rst_neg;
  wire led_neg, cs_neg, sck_neg, mo_neg, mi_neg;
  spi_disk_model #(.LOAD(1), .FILE("sim/out/disk.bin")) flash_neg (
    .clk (clk), .cs_n (cs_neg), .sclk (sck_neg), .mosi (mo_neg), .miso (mi_neg)
  );
  spi_disk_reader #(.EXPECT_BUILD(BUILD_NO), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_neg (
    .clk (clk), .rst (rst_neg), .led (led_neg),
    .spi_cs_n (cs_neg), .spi_clk (sck_neg), .spi_mosi (mo_neg), .spi_miso (mi_neg)
  );

  reg rst_bad;
  wire led_bad, cs_bad, sck_bad, mo_bad, mi_bad;
  spi_disk_model #(.LOAD(1), .FILE("sim/out/disk.bin")) flash_bad (
    .clk (clk), .cs_n (cs_bad), .sclk (sck_bad), .mosi (mo_bad), .miso (mi_bad)
  );
  spi_disk_reader #(.EXPECT_BUILD(BUILD_YES), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_bad (
    .clk (clk), .rst (rst_bad), .led (led_bad),
    .spi_cs_n (cs_bad), .spi_clk (sck_bad), .spi_mosi (mo_bad), .spi_miso (mi_bad)
  );

  reg rst_blank;
  wire led_blank, cs_blank, sck_blank, mo_blank, mi_blank;
  spi_disk_model #(.LOAD(0)) flash_blank (
    .clk (clk), .cs_n (cs_blank), .sclk (sck_blank), .mosi (mo_blank), .miso (mi_blank)
  );
  spi_disk_reader #(.EXPECT_BUILD(BUILD_YES), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_blank (
    .clk (clk), .rst (rst_blank), .led (led_blank),
    .spi_cs_n (cs_blank), .spi_clk (sck_blank), .spi_mosi (mo_blank), .spi_miso (mi_blank)
  );

  initial begin
    rst_ok = 1'b1;
    rst_neg = 1'b1;
    rst_bad = 1'b1;
    rst_blank = 1'b1;
    repeat (4) @(posedge clk);
    flash_bad.mem[20] = flash_bad.mem[20] ^ 8'h01;
    rst_ok = 1'b0;
    rst_neg = 1'b0;
    rst_bad = 1'b0;
    rst_blank = 1'b0;
  end

  initial begin
    wait (done_ok && done_neg && done_bad && done_blank);
    $display("SPI_DISK PASS all");
    $display("SPI_DISK rate half=%0d build=%0h neg=%0h base=%0h",
             6750000, BUILD_YES, BUILD_NO, BASE);
    $finish;
  end

  reg [7:0] wb0, wb1, wb2, wb3;
  reg [31:0] wsum;
  integer wi;
  integer wn;

  task load_word;
    input integer which;
    input integer off;
    begin
      if (which == 0) begin
        wb0 = flash_ok.mem[off];
        wb1 = flash_ok.mem[off+1];
        wb2 = flash_ok.mem[off+2];
        wb3 = flash_ok.mem[off+3];
      end else begin
        wb0 = flash_bad.mem[off];
        wb1 = flash_bad.mem[off+1];
        wb2 = flash_bad.mem[off+2];
        wb3 = flash_bad.mem[off+3];
      end
    end
  endtask

  task sum_payload;
    input integer which;
    begin
      load_word(which, 12);
      wn = {wb3, wb2, wb1, wb0};
      wsum = 32'd0;
      for (wi = 0; wi < wn; wi = wi + 4) begin
        load_word(which, 20 + wi);
        wsum = wsum + {wb3, wb2, wb1, wb0};
      end
    end
  endtask

  initial begin
    integer n;
    integer guard;
    wait (rst_ok == 1'b0);
    guard = 0;
    while (dut_ok.pass !== 1'b1 && guard < 2000000) begin
      @(posedge clk);
      guard = guard + 1;
      if (led_ok !== 1'b0)
        fail("reader blinked before the checksum");
    end
    if (dut_ok.pass !== 1'b1)
      fail("reader did not pass");
    @(posedge clk);
    sum_payload(0);
    $display("SPI_DISK read magic %08x build %08x len %0d sum %08x bytes %0d",
             dut_ok.hdr_magic, dut_ok.hdr_build, wn, dut_ok.got_sum, flash_ok.bytes_out);
    if (dut_ok.hdr_magic !== 32'h314B5344 || dut_ok.hdr_version !== 32'h1)
      fail("header magic or version");
    if (dut_ok.hdr_build !== BUILD_YES)
      fail("header build");
    if (dut_ok.got_sum !== wsum || dut_ok.hdr_sum !== wsum)
      fail("checksum");
    if (flash_ok.bytes_out !== 20 + wn)
      fail("read length");
    if (flash_ok.read_cmds !== 1 || flash_ok.other_cmds !== 0)
      fail("reader used a command other than one 03h");
    if (flash_ok.first_addr !== BASE || flash_ok.bad_addr !== 0)
      fail("reader left 0x200000");
    n = 0;
    while (led_ok !== 1'b1 && n < 100) begin
      @(posedge clk);
      n = n + 1;
    end
    if (led_ok !== 1'b1)
      fail("reader led stayed dark");
    n = 0;
    while (led_ok == 1'b1) begin
      @(posedge clk);
      n = n + 1;
      if (n > BLINK + 5)
        fail("reader high half too long");
    end
    $display("SPI_DISK read high-half %0d", n);
    if (n < BLINK - 1 || n > BLINK + 1)
      fail("reader blink half");
    $display("SPI_DISK PASS read");
    done_ok = 1'b1;
  end

  initial begin
    integer guard;
    integer n;
    wait (rst_neg == 1'b0);
    guard = 0;
    while (dut_neg.state !== 3'd4 && guard < 200000) begin
      @(posedge clk);
      guard = guard + 1;
      if (led_neg !== 1'b0)
        fail("negative reader blinked");
    end
    if (dut_neg.state !== 3'd4)
      fail("negative reader did not halt");
    if (dut_neg.pass !== 1'b0)
      fail("negative reader passed");
    if (dut_neg.hdr_build !== BUILD_YES)
      fail("negative reader did not see the image build");
    if (flash_neg.other_cmds !== 0 || flash_neg.read_cmds !== 1)
      fail("negative reader wrote or skipped the read");
    if (flash_neg.first_addr !== BASE || flash_neg.bad_addr !== 0)
      fail("negative reader left 0x200000");
    if (flash_neg.bytes_out !== 20)
      fail("negative reader read past the header");
    for (n = 0; n < 400; n = n + 1) begin
      @(posedge clk);
      if (led_neg !== 1'b0)
        fail("negative led rose");
    end
    $display("SPI_DISK PASS neg");
    done_neg = 1'b1;
  end

  initial begin
    integer guard;
    integer n;
    wait (rst_bad == 1'b0);
    guard = 0;
    while (dut_bad.state !== 3'd4 && guard < 2000000) begin
      @(posedge clk);
      guard = guard + 1;
      if (led_bad !== 1'b0)
        fail("corrupt reader blinked");
    end
    if (dut_bad.state !== 3'd4)
      fail("corrupt reader did not halt");
    @(posedge clk);
    if (dut_bad.pass !== 1'b0)
      fail("corrupt reader passed");
    wait (done_ok == 1'b1);
    sum_payload(1);
    if (dut_bad.hdr_build !== BUILD_YES || dut_bad.hdr_magic !== 32'h314B5344)
      fail("corrupt reader lost the header");
    if (dut_bad.got_sum === dut_bad.hdr_sum || dut_bad.got_sum !== wsum)
      fail("corrupt checksum was not the damaged payload");
    if (flash_bad.other_cmds !== 0 || flash_bad.bad_addr !== 0)
      fail("corrupt reader wrote or left the image");
    for (n = 0; n < 400; n = n + 1) begin
      @(posedge clk);
      if (led_bad !== 1'b0)
        fail("corrupt led rose");
    end
    $display("SPI_DISK PASS corrupt");
    done_bad = 1'b1;
  end

  initial begin
    integer guard;
    integer n;
    wait (rst_blank == 1'b0);
    guard = 0;
    while (dut_blank.state !== 3'd4 && guard < 200000) begin
      @(posedge clk);
      guard = guard + 1;
      if (led_blank !== 1'b0)
        fail("blank reader blinked");
    end
    if (dut_blank.state !== 3'd4)
      fail("blank reader did not halt");
    if (dut_blank.pass !== 1'b0)
      fail("blank reader passed");
    if (flash_blank.other_cmds !== 0)
      fail("blank reader wrote");
    for (n = 0; n < 200; n = n + 1) begin
      @(posedge clk);
      if (led_blank !== 1'b0)
        fail("blank led rose");
    end
    $display("SPI_DISK PASS blank");
    done_blank = 1'b1;
  end

  initial begin
    #80_000_000;
    if (!(done_ok && done_neg && done_bad && done_blank))
      fail("timeout");
  end
endmodule
