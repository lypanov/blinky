// Functional sim of the SPI-flash pathfinder. SPI and blink dividers
// are shortened; the FPGA images keep the published half-periods.
`timescale 1ns/1ps

module tb_spi_flash_pathfinder;
  localparam integer BLINK = 20;
  localparam integer SPIH = 1;
  localparam [7:0] BUILD_YES = 8'h7B;
  localparam [7:0] BUILD_NO = 8'h7C;

  reg clk;
  initial clk = 1'b0;
  always #5 clk = ~clk;

  reg done_id = 1'b0;
  reg done_bad = 1'b0;
  reg done_blank = 1'b0;
  reg done_chain = 1'b0;

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

  task fail;
    input [255:0] msg;
    begin
      $display("SPI_FLASH FAIL %0s", msg);
      $fatal(1);
    end
  endtask

  // ------------------------------------------------------------------
  // JEDEC match blinks. A wrong ID stays dark and does not erase.
  // ------------------------------------------------------------------
  reg rst_id;
  wire led_id;
  wire cs_id, sck_id, mo_id, mi_id;
  spi_flash_model flash_id (
    .clk (clk), .cs_n (cs_id), .sclk (sck_id), .mosi (mo_id), .miso (mi_id)
  );
  spi_flash_pathfinder #(.MODE(0), .BUILD(BUILD_YES), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_id (
    .clk (clk), .rst (rst_id), .led (led_id),
    .spi_cs_n (cs_id), .spi_clk (sck_id), .spi_mosi (mo_id), .spi_miso (mi_id)
  );

  reg rst_bad;
  wire led_bad;
  wire cs_bad, sck_bad, mo_bad, mi_bad;
  spi_flash_model #(.ID0(8'hEF), .ID1(8'h40), .ID2(8'h16)) flash_bad (
    .clk (clk), .cs_n (cs_bad), .sclk (sck_bad), .mosi (mo_bad), .miso (mi_bad)
  );
  spi_flash_pathfinder #(.MODE(1), .BUILD(BUILD_YES), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_bad (
    .clk (clk), .rst (rst_bad), .led (led_bad),
    .spi_cs_n (cs_bad), .spi_clk (sck_bad), .spi_mosi (mo_bad), .spi_miso (mi_bad)
  );

  reg rst_blank;
  wire led_blank;
  wire cs_blank, sck_blank, mo_blank, mi_blank;
  spi_flash_model flash_blank (
    .clk (clk), .cs_n (cs_blank), .sclk (sck_blank), .mosi (mo_blank), .miso (mi_blank)
  );
  spi_flash_pathfinder #(.MODE(2), .BUILD(BUILD_YES), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_blank (
    .clk (clk), .rst (rst_blank), .led (led_blank),
    .spi_cs_n (cs_blank), .spi_clk (sck_blank), .spi_mosi (mo_blank), .spi_miso (mi_blank)
  );

  // Writer, then a fresh reader, then the negative reader. One NOR.
  reg rst_wr, rst_rd, rst_neg;
  reg [1:0] sel;
  wire led_wr, led_rd, led_neg;
  wire cs_wr, sck_wr, mo_wr;
  wire cs_rd, sck_rd, mo_rd;
  wire cs_neg, sck_neg, mo_neg;
  wire cs_ch, sck_ch, mo_ch, mi_ch;
  wire led_ch;
  assign cs_ch = (sel == 2'd0) ? cs_wr : (sel == 2'd1) ? cs_rd : cs_neg;
  assign sck_ch = (sel == 2'd0) ? sck_wr : (sel == 2'd1) ? sck_rd : sck_neg;
  assign mo_ch = (sel == 2'd0) ? mo_wr : (sel == 2'd1) ? mo_rd : mo_neg;
  assign led_ch = (sel == 2'd0) ? led_wr : (sel == 2'd1) ? led_rd : led_neg;
  spi_flash_model flash_ch (
    .clk (clk), .cs_n (cs_ch), .sclk (sck_ch), .mosi (mo_ch), .miso (mi_ch)
  );
  spi_flash_pathfinder #(.MODE(1), .BUILD(BUILD_YES), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_wr (
    .clk (clk), .rst (rst_wr), .led (led_wr),
    .spi_cs_n (cs_wr), .spi_clk (sck_wr), .spi_mosi (mo_wr), .spi_miso (mi_ch)
  );
  spi_flash_pathfinder #(.MODE(2), .BUILD(BUILD_YES), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_rd (
    .clk (clk), .rst (rst_rd), .led (led_rd),
    .spi_cs_n (cs_rd), .spi_clk (sck_rd), .spi_mosi (mo_rd), .spi_miso (mi_ch)
  );
  spi_flash_pathfinder #(.MODE(2), .BUILD(BUILD_NO), .BLINK_HALF(BLINK), .SPI_HALF(SPIH)) dut_neg (
    .clk (clk), .rst (rst_neg), .led (led_neg),
    .spi_cs_n (cs_neg), .spi_clk (sck_neg), .spi_mosi (mo_neg), .spi_miso (mi_ch)
  );

  initial begin
    rst_id = 1'b1;
    rst_bad = 1'b1;
    rst_blank = 1'b1;
    rst_wr = 1'b1;
    rst_rd = 1'b1;
    rst_neg = 1'b1;
    sel = 2'd0;
    repeat (4) @(posedge clk);
    rst_id = 1'b0;
    rst_bad = 1'b0;
    rst_blank = 1'b0;
    rst_wr = 1'b0;
  end

  initial begin
    wait (done_id && done_bad && done_blank && done_chain);
    $display("SPI_FLASH PASS all");
    $display("SPI_FLASH rates A=%0d Hz-half B=%0d C=%0d build=%02x neg=%02x page=%06x",
             9000000, 5400000, 3375000, BUILD_YES, BUILD_NO, 24'h3FF000);
    $finish;
  end

  initial begin
    integer n;
    integer guard;
    wait (rst_id == 1'b0);
    guard = 0;
    while (dut_id.pass !== 1'b1 && guard < 20000) begin
      @(posedge clk);
      guard = guard + 1;
    end
    if (dut_id.pass !== 1'b1)
      fail("id image did not pass");
    $display("SPI_FLASH id bytes %02x %02x %02x", dut_id.id0, dut_id.id1, dut_id.id2);
    if (dut_id.id0 !== 8'h85 || dut_id.id1 !== 8'h60 || dut_id.id2 !== 8'h16)
      fail("id bytes");
    if (flash_id.erase_count !== 0 || flash_id.prog_count !== 0)
      fail("id image wrote the array");
    n = 0;
    while (led_id !== 1'b1 && n < 100) begin
      @(posedge clk);
      n = n + 1;
    end
    if (led_id !== 1'b1)
      fail("id led stayed dark");
    n = 0;
    while (led_id == 1'b1) begin
      @(posedge clk);
      n = n + 1;
      if (n > BLINK + 5)
        fail("id high half too long");
    end
    $display("SPI_FLASH id high-half %0d", n);
    if (n < BLINK - 1 || n > BLINK + 1)
      fail("id blink half");
    $display("SPI_FLASH PASS id");
    done_id = 1'b1;
  end

  initial begin
    integer guard;
    integer n;
    wait (rst_bad == 1'b0);
    guard = 0;
    while (dut_bad.state !== 3'd4 && guard < 20000) begin
      @(posedge clk);
      guard = guard + 1;
      if (led_bad !== 1'b0)
        fail("bad id blinked");
    end
    if (dut_bad.state !== 3'd4)
      fail("bad id did not halt");
    if (dut_bad.pass !== 1'b0)
      fail("bad id passed");
    if (flash_bad.erase_count !== 0 || flash_bad.prog_count !== 0)
      fail("bad id erased or programmed");
    for (n = 0; n < 400; n = n + 1) begin
      @(posedge clk);
      if (led_bad !== 1'b0)
        fail("bad id led rose after halt");
    end
    $display("SPI_FLASH PASS bad-id");
    done_bad = 1'b1;
  end

  initial begin
    integer guard;
    integer n;
    wait (rst_blank == 1'b0);
    guard = 0;
    while (dut_blank.state !== 3'd4 && guard < 80000) begin
      @(posedge clk);
      guard = guard + 1;
      if (led_blank !== 1'b0)
        fail("blank reader blinked");
    end
    if (dut_blank.pass !== 1'b0)
      fail("blank reader passed");
    if (flash_blank.erase_count !== 0 || flash_blank.prog_count !== 0)
      fail("blank reader wrote");
    for (n = 0; n < 200; n = n + 1) begin
      @(posedge clk);
      if (led_blank !== 1'b0)
        fail("blank led rose");
    end
    $display("SPI_FLASH PASS blank");
    done_blank = 1'b1;
  end

  initial begin
    integer guard;
    integer n;
    integer i;
    wait (rst_wr == 1'b0);
    guard = 0;
    while (dut_wr.pass !== 1'b1 && guard < 100000) begin
      @(posedge clk);
      guard = guard + 1;
    end
    if (dut_wr.pass !== 1'b1) begin
      $display("SPI_FLASH writer debug pass=%b state=%0d step=%0d id=%02x %02x %02x mismatch=%b erase=%0d prog=%0d bytes=%0d bad_addr=%0d bad_cmd=%0d mem0=%02x wip_seen=%0d status=%0d",
               dut_wr.pass, dut_wr.state, dut_wr.step, dut_wr.id0, dut_wr.id1, dut_wr.id2, dut_wr.mismatch,
               flash_ch.erase_count, flash_ch.prog_count, flash_ch.prog_bytes, flash_ch.bad_addr, flash_ch.bad_cmd,
               flash_ch.mem[0], flash_ch.wip_seen, flash_ch.status_reads);
      for (i = 0; i < 16; i = i + 1)
        $display("  mem[%0d]=%02x expect %02x", i, flash_ch.mem[i], page_byte(i[7:0], BUILD_YES));
      begin : scan
        integer bad;
        bad = 0;
        for (i = 0; i < 256; i = i + 1)
          if (flash_ch.mem[i] !== page_byte(i[7:0], BUILD_YES))
            bad = bad + 1;
        $display("  mismatched bytes %0d", bad);
      end
      fail("writer did not pass");
    end
    if (flash_ch.erase_count !== 1 || flash_ch.erase_addr !== 24'h3FF000)
      fail("erase was not the last sector once");
    if (flash_ch.prog_count !== 1 || flash_ch.prog_addr !== 24'h3FF000)
      fail("program was not the last page once");
    if (flash_ch.prog_len !== 256)
      fail("program length");
    if (flash_ch.bad_addr !== 0 || flash_ch.bad_cmd !== 0)
      fail("writer used a bad address or command");
    for (i = 0; i < 256; i = i + 1) begin
      if (flash_ch.mem[i] !== page_byte(i[7:0], BUILD_YES)) begin
        $display("SPI_FLASH mem[%0d]=%02x expect %02x", i, flash_ch.mem[i], page_byte(i[7:0], BUILD_YES));
        fail("programmed byte");
      end
    end
    for (i = 256; i < 4096; i = i + 1) begin
      if (flash_ch.mem[i] !== 8'hFF)
        fail("erased byte outside the page");
    end
    n = 0;
    while (led_wr !== 1'b1 && n < 100) begin
      @(posedge clk);
      n = n + 1;
    end
    n = 0;
    while (led_wr == 1'b1) begin
      @(posedge clk);
      n = n + 1;
      if (n > BLINK + 5)
        fail("writer high half too long");
    end
    $display("SPI_FLASH write high-half %0d", n);
    if (n < BLINK - 1 || n > BLINK + 1)
      fail("writer blink half");
    $display("SPI_FLASH PASS write");

    // Fresh SRAM image: new reader, same NOR.
    sel = 2'd1;
    repeat (4) @(posedge clk);
    rst_rd = 1'b0;
    guard = 0;
    while (dut_rd.pass !== 1'b1 && guard < 100000) begin
      @(posedge clk);
      guard = guard + 1;
    end
    if (dut_rd.pass !== 1'b1)
      fail("reader did not pass");
    if (flash_ch.erase_count !== 1 || flash_ch.prog_count !== 1)
      fail("reader modified the array");
    n = 0;
    while (led_rd !== 1'b1 && n < 100) begin
      @(posedge clk);
      n = n + 1;
    end
    n = 0;
    while (led_rd == 1'b1) begin
      @(posedge clk);
      n = n + 1;
      if (n > BLINK + 5)
        fail("reader high half too long");
    end
    $display("SPI_FLASH read high-half %0d", n);
    if (n < BLINK - 1 || n > BLINK + 1)
      fail("reader blink half");
    $display("SPI_FLASH PASS read");

    sel = 2'd2;
    repeat (4) @(posedge clk);
    rst_neg = 1'b0;
    guard = 0;
    while (dut_neg.state !== 3'd4 && guard < 100000) begin
      @(posedge clk);
      guard = guard + 1;
      if (led_neg !== 1'b0)
        fail("negative reader blinked");
    end
    if (dut_neg.pass !== 1'b0)
      fail("negative reader passed");
    if (flash_ch.erase_count !== 1 || flash_ch.prog_count !== 1)
      fail("negative reader wrote");
    for (n = 0; n < 400; n = n + 1) begin
      @(posedge clk);
      if (led_neg !== 1'b0)
        fail("negative led rose");
    end
    $display("SPI_FLASH PASS neg");
    done_chain = 1'b1;
  end

  initial begin
    #5_000_000;
    if (!(done_id && done_bad && done_blank && done_chain))
      fail("timeout");
  end
endmodule
