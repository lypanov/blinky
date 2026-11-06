// Icarus integration bench for the soft DDR3 controller.
// Layers: this file, sim/micron/ddr3.v, Gowin gw2a prim_sim.v.
// It does not use sim/Ddr3UserModel.v. It does not measure a Dock eye.
//
// The pass line is the DDR3_800 silicon slot, dq_in[0], which is
// dout128[127:112]. dout under SIM is dq_in[4]. A hit only in
// that slot is a failure.

`timescale 1ps / 1ps

module tb_ddr3_phy;
    localparam integer PCLK_WAIT = 200000; // level, read gate, then the write-eye walk
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

    wire        ddr_nrst, ddr_ck, cke_ctl, cs_n, ras_n, cas_n, we_n, odt;
    wire        cke;
    // CKE is a register on pclk, and pclk is aligned with ck.
    // The pad delay is what gives tIH. 400 ps is past the sg25
    // 275 ps hold and leaves the next edge its 350 ps setup.
    assign #400 cke = cke_ctl;
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
        .DDR3_CKE(cke_ctl),
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

    // The controller samples din at the DQ beat, several pclk after
    // wr. A nonblocking update on the same edge as wait(busy) lets
    // the next command overwrite din before that beat.
    task do_write;
        input [25:0] a;
        input [15:0] v;
        begin
            wait (busy === 1'b0);
            @(posedge pclk);
            #1;
            wr = 1'b1;
            rd = 1'b0;
            refresh = 1'b0;
            addr = a;
            din = v;
            @(posedge pclk);
            #1;
            wr = 1'b0;
            if (busy !== 1'b1)
                wait (busy === 1'b1);
            wait (busy === 1'b0);
        end
    endtask

    task do_refresh;
        begin
            wait (busy === 1'b0);
            @(posedge pclk);
            #1;
            refresh = 1'b1;
            wr = 1'b0;
            rd = 1'b0;
            @(posedge pclk);
            #1;
            refresh = 1'b0;
            if (busy !== 1'b1)
                wait (busy === 1'b1);
            wait (busy === 1'b0);
            // The controller ends refresh at tRC (20 nCK). The
            // model requires tRFC, 110 ns, before the next ACT.
            waits = 0;
            while (waits < 8) begin
                @(posedge pclk);
                waits = waits + 1;
            end
        end
    endtask

    // Score dq_in[0] at data_ready. Other slots and later cycles are
    // printed and do not pass the run.
    task do_read;
        input [25:0] a;
        input [15:0] exp;
        integer s;
        reg [15:0] slice;
        begin
            wait (busy === 1'b0);
            @(posedge pclk);
            #1;
            rd = 1'b1;
            wr = 1'b0;
            refresh = 1'b0;
            addr = a;
            @(posedge pclk);
            #1;
            rd = 1'b0;
            saw = 1'b0;
            slot0 = 16'hxxxx;
            slot4 = 16'hxxxx;
            waits = 0;
            while (waits < READY_WAIT) begin
                @(posedge pclk);
                #1;
                waits = waits + 1;
                $display("RSAMP %0d addr=%h ready=%b raw=%h",
                         waits, a, data_ready, dout128);
                for (s = 0; s < 8; s = s + 1) begin
                    slice = dout128[127 - s*16 -: 16];
                    if (slice === exp && data_ready === 1'b1)
                        $display("HIT addr=%h pclk=%0d slot=%0d", a, waits, s);
                    // 1111 in the Dock slot at data_ready, on the
                    // column-1 read, is the even-word alias.
                    if (exp === 16'h2222 && slice === 16'h1111
                            && data_ready === 1'b1 && s == 0)
                        $display("ALIAS addr=%h pclk=%0d slot=%0d even=1111",
                                 a, waits, s);
                end
                if (data_ready === 1'b1 && !saw) begin
                    slot0 = dout128[127:112];
                    slot4 = dout128[63:48];
                    saw = 1'b1;
                end
                if (saw && waits > 4 && busy === 1'b0)
                    waits = READY_WAIT;
            end
            $display("READ addr=%h dock_slot=%h sim_slot=%h sim_dout=%h ready=%b exp=%h",
                     a, slot0, slot4, dout, saw, exp);
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

    // One line per read. pre/at/post are dq_in[0] on the pclk
    // before data_ready, at data_ready, and one pclk after.
    // The score does not use this task.
    task do_read_phase;
        input [25:0] a;
        reg [15:0] pre, at, post, prev;
        reg got;
        begin
            wait (busy === 1'b0);
            @(posedge pclk);
            #1;
            rd = 1'b1;
            wr = 1'b0;
            refresh = 1'b0;
            addr = a;
            @(posedge pclk);
            #1;
            rd = 1'b0;
            got = 1'b0;
            pre = 16'hxxxx;
            at = 16'hxxxx;
            post = 16'hxxxx;
            prev = 16'hxxxx;
            waits = 0;
            while (waits < READY_WAIT && !got) begin
                @(posedge pclk);
                #1;
                waits = waits + 1;
                if (data_ready === 1'b1) begin
                    pre = prev;
                    at = dout128[127:112];
                    @(posedge pclk);
                    #1;
                    post = dout128[127:112];
                    got = 1'b1;
                end
                prev = dout128[127:112];
            end
            $display("PHASE rp=%0d rs=%0d addr=%h pre=%h at=%h post=%h raw=%h",
                     ctl.rclkpos, ctl.rclksel, a, pre, at, post, dout128);
            $fflush;
            wait (busy === 1'b0);
        end
    endtask

    integer pin_left;
    reg phase_sweep;
    initial begin
        pin_left = 0;
        phase_sweep = 1'b0;
    end
    // The command is on the pin for one ck. The next edges are the
    // preamble and the burst, which is where DM and DQ have to be
    // a real 0 or 1.
    always @(posedge ddr_ck) begin
        if (!phase_sweep && rcalib_done && {cs_n, ras_n, cas_n, we_n} === 4'b0100) begin
            $display("CMD write ba=%h a=%h", ba, a);
            pin_left = 10;
        end
        if (!phase_sweep && rcalib_done && {cs_n, ras_n, cas_n, we_n} === 4'b0101) begin
            $display("CMD read ba=%h a=%h", ba, a);
            pin_left = 10;
        end
        if (pin_left > 0) begin
            $display("PIN dm=%b dqs=%b dq=%h", dm, dqs, dq);
            pin_left = pin_left - 1;
        end
    end

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
        // Diagnostic only. The default run does not take this branch.
        // It moves the read gate across the burst and prints dq_in[0].
        if ($test$plusargs("phase_sweep")) begin
            phase_sweep = 1'b1;
            begin : sweep
                integer rp, rs;
                for (rp = 0; rp < 3; rp = rp + 1) begin
                    for (rs = 0; rs < 8; rs = rs + 1) begin
                        if ((rp == 1) || (rp == 0 && rs >= 4) || (rp == 2 && rs < 4)) begin
                            force ctl.rclkpos = rp[1:0];
                            force ctl.rclksel = rs[2:0];
                            #1;
                            do_read_phase(26'h000000);
                            do_read_phase(26'h000001);
                            do_read_phase(26'h000010);
                        end
                    end
                end
            end
            release ctl.rclkpos;
            release ctl.rclksel;
            $display("PHY_SCORE fail");
            $finish;
        end
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
