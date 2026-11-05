// Icarus integration bench for the soft DDR3 controller.
// Layers: this file, sim/micron/ddr3.v, Gowin gw2a prim_sim.v.
// It does not use sim/Ddr3UserModel.v. It does not measure a Dock eye.
//
// The pass line is the DDR3_800 silicon slot, dq_in[0], which is
// dout128[127:112]. dout under SIM is dq_in[4]. A hit only in
// that slot is a failure.

`timescale 1ps / 1ps

module tb_ddr3_phy;
    localparam integer PCLK_WAIT = 2500; // 25 us. Covers tZQinit plus a short level search.
    localparam integer READY_WAIT = 40;

    reg        rst_n;
    reg        pclk;
    reg        fclk;
    reg        ck;
    reg        rd, wr, refresh;
    reg [25:0] addr;
    reg [15:0] din;

    wire [15:0] dout;
    wire [127:0] dout128;
    wire        data_ready, busy;
    wire [7:0]  wstep, wstep1, wstep_run, wstep1_run;
    wire [1:0]  rclkpos;
    wire [2:0]  rclksel;
    wire        wlevel_done, rcalib_done;

    wire        ddr_nrst, ddr_ck, cke, cs_n, ras_n, cas_n, we_n, odt;
    wire [2:0]  ba;
    wire [12:0] a;
    wire [1:0]  dm;
    wire [15:0] dq;
    wire [1:0]  dqs;
    wire [1:0]  dqs_n;
    wire [1:0]  tdqs_n;

    // The controller drives DQS single-ended. Drive the complement
    // while it drives, and release it when DQS is z so the model
    // can drive the pair on a read.
    assign dqs_n[0] = (dqs[0] === 1'bz) ? 1'bz : ~dqs[0];
    assign dqs_n[1] = (dqs[1] === 1'bz) ? 1'bz : ~dqs[1];

    // prim_sim names this instance from inside DQS when GSREN is true.
    GSR GSR (.GSRI(1'b1));

    ddr3 mem (
        .rst_n(ddr_nrst),
        .ck(ddr_ck),
        .ck_n(~ddr_ck),
        .cke(cke),
        .cs_n(cs_n),
        .ras_n(ras_n),
        .cas_n(cas_n),
        .we_n(we_n),
        .dm_tdqs(dm),
        .ba(ba),
        .addr(a),
        .dq(dq),
        .dqs(dqs),
        .dqs_n(dqs_n),
        .tdqs_n(tdqs_n),
        .odt(odt)
    );
    defparam mem.DEBUG = 0;
    defparam mem.STOP_ON_ERROR = 0;

    ddr3_controller #(
        .ROW_WIDTH(13),
        .COL_WIDTH(10)
    ) ctl (
        .pclk(pclk),
        .fclk(fclk),
        .ck(ck),
        .resetn(rst_n),
        .rd(rd),
        .wr(wr),
        .refresh(refresh),
        .addr(addr),
        .din(din),
        .dout(dout),
        .dout128(dout128),
        .data_ready(data_ready),
        .busy(busy),
        .write_level_done(wlevel_done),
        .wstep(wstep),
        .wstep1(wstep1),
        .wstep_run(wstep_run),
        .wstep1_run(wstep1_run),
        .step0_ov(8'd0),
        .step1_ov(8'd0),
        .step_ov_en(1'b0),
        .read_calib_done(rcalib_done),
        .rclkpos(rclkpos),
        .rclksel(rclksel),
        .debug(),
        .DDR3_DQ(dq),
        .DDR3_DQS(dqs),
        .DDR3_A(a),
        .DDR3_BA(ba),
        .DDR3_nRAS(ras_n),
        .DDR3_nCAS(cas_n),
        .DDR3_nWE(we_n),
        .DDR3_nCS(cs_n),
        .DDR3_CK(ddr_ck),
        .DDR3_CKE(cke),
        .DDR3_nRESET(ddr_nrst),
        .DDR3_DM(dm),
        .DDR3_ODT(odt)
    );

    // pclk 100 MHz, fclk 400 MHz. ck lags fclk by 90 degrees:
    // the controller's comment says the PLL delays fclk to make ck.
    // The other order (ck leading fclk) was run once. Writes then
    // failed tDQSS, tDSS, and the latching-edge check, and both
    // read slots came back X.
    real tck;
    initial begin
        tck = 2500.0;
        fclk = 1'b1;
        ck = 1'b1;
        pclk = 1'b1;
        forever begin
            #(tck/4) fclk = ~fclk;
            #(tck/4) ck = ~ck;
            #(tck/4) fclk = ~fclk;
            #(tck/4) ck = ~ck;
            #(tck/4) fclk = ~fclk;
            #(tck/4) ck = ~ck;
            #(tck/4) fclk = ~fclk;
            #(tck/4) ck = ~ck;
            pclk = ~pclk;
        end
    end

    integer fails;
    integer waits;
    reg [15:0] slot0;
    reg [15:0] slot4;
    reg        saw;

    task wait_idle;
        begin
            waits = 0;
            while (busy !== 1'b0 && waits < READY_WAIT) begin
                @(posedge pclk);
                waits = waits + 1;
            end
            if (busy !== 1'b0) begin
                $display("FAIL busy stayed high");
                fails = fails + 1;
            end
        end
    endtask

    task do_write;
        input [25:0] a;
        input [15:0] v;
        begin
            wait_idle;
            @(posedge pclk);
            wr <= 1'b1;
            rd <= 1'b0;
            refresh <= 1'b0;
            addr <= a;
            din <= v;
            @(posedge pclk);
            wr <= 1'b0;
        end
    endtask

    task do_refresh;
        begin
            wait_idle;
            @(posedge pclk);
            refresh <= 1'b1;
            wr <= 1'b0;
            rd <= 1'b0;
            @(posedge pclk);
            refresh <= 1'b0;
        end
    endtask

    // Sample the beat the Dock uses. dout under SIM is the other slot.
    task do_read;
        input [25:0] a;
        input [15:0] exp;
        begin
            wait_idle;
            @(posedge pclk);
            rd <= 1'b1;
            wr <= 1'b0;
            refresh <= 1'b0;
            addr <= a;
            @(posedge pclk);
            rd <= 1'b0;
            saw = 1'b0;
            slot0 = 16'hxxxx;
            slot4 = 16'hxxxx;
            waits = 0;
            while (waits < READY_WAIT) begin
                @(posedge pclk);
                waits = waits + 1;
                if (data_ready === 1'b1) begin
                    slot0 = dout128[127:112];
                    slot4 = dout128[63:48];
                    saw = 1'b1;
                    waits = READY_WAIT;
                end
            end
            $display("READ addr=%h dock_slot=%h sim_slot=%h sim_dout=%h ready=%b exp=%h raw=%h",
                     a, slot0, slot4, dout, saw, exp, dout128);
            // The score uses the data_ready cycle. Print the next few
            // dock-slot samples so a late capture is visible and is
            // not counted as a pass.
            if (saw) begin
                waits = 0;
                while (waits < 4) begin
                    @(posedge pclk);
                    waits = waits + 1;
                    $display("READ+ %0d addr=%h dock_slot=%h",
                             waits, a, dout128[127:112]);
                end
            end
            if (!saw) begin
                $display("FAIL addr=%h data_ready did not rise", a);
                fails = fails + 1;
            end else if (slot0 !== exp) begin
                fails = fails + 1;
                if (slot4 === exp && slot0 !== slot4)
                    $display("FAIL addr=%h dock slot miss, SIM slot hit", a);
                else if (exp === 16'h2222 && slot0 === 16'h1111)
                    $display("FAIL addr=%h even-word alias", a);
                else
                    $display("FAIL addr=%h dock slot mismatch", a);
            end
        end
    endtask

    initial begin
        fails = 0;
        rst_n = 1'b0;
        rd = 1'b0;
        wr = 1'b0;
        refresh = 1'b0;
        addr = 26'd0;
        din = 16'd0;
        if ($test$plusargs("dump")) begin
            $dumpfile("sim/obj_dir/ddr3_phy.vcd");
            $dumpvars(1, tb_ddr3_phy);
        end

        #10000;
        @(negedge ck);
        rst_n = 1'b1;

        waits = 0;
        while (rcalib_done !== 1'b1 && waits < PCLK_WAIT) begin
            @(posedge pclk);
            waits = waits + 1;
            if (waits == 1 || waits % 200 == 0) begin
                $display("WAIT cyc=%0d calib=%b wstep=%0d/%0d run=%0d/%0d",
                         waits, rcalib_done, wstep, wstep1, wstep_run, wstep1_run);
                $fflush;
            end
        end
        $display("CALIB done=%b wstep=%h/%h run=%h/%h rclkpos=%h rclksel=%h cycles=%0d",
                 rcalib_done, wstep, wstep1, wstep_run, wstep1_run,
                 rclkpos, rclksel, waits);
        if (rcalib_done !== 1'b1) begin
            $display("FAIL read calibration did not finish");
            fails = fails + 1;
            $display("PHY_SCORE fail");
            $finish;
        end

        // Traffic starts here. Micron ERROR lines after this marker
        // are command failures. Lines before it are the shortened
        // SIM reset and ZQ.
        $display("PHY_TRAFFIC");

        // Column 0 and column 1 are one BC4 pair. Different data.
        do_write(26'h000000, 16'h1111);
        do_write(26'h000001, 16'h2222);
        do_write(26'h000010, 16'h3333);
        do_refresh;
        do_read(26'h000000, 16'h1111);
        do_read(26'h000001, 16'h2222);
        do_read(26'h000010, 16'h3333);

        if (fails == 0)
            $display("PHY_SCORE pass");
        else
            $display("PHY_SCORE fail");
        $finish;
    end
endmodule
