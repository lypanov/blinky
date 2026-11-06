// CPU image on the Icarus + Micron ddr3.v + prim_sim controller.
// The command port is CPUSimTop's phy_* bundle. sim/Ddr3UserModel.v
// is not instantiated.
//
// The CPU is given dout128[127:112], which is dq_in[0]. The
// controller's SIM dout is dq_in[4] and is left unconnected.
// Clocks, the 400 ps CKE delay, and the DQS complement match
// tb_ddr3_phy.v. step overrides stay off. The one-CK read backup
// is the controller's `ifdef SIM path; it is not a bitstream step.

`timescale 1ps / 1ps

module tb_ddr3_cpu_phy;
    localparam integer PCLK_WAIT = 200000;
    localparam integer EXPECT_PERIOD = 3668; // 576*5+788, delay loop only
    // ModDesc and Files both sit before that loop, so the period stays.
    localparam [31:0] EXPECT_R5 = 32'h00000000;
    // ModDesc leaves R9 at 8. Files uses R9 as the w accumulator and
    // leaves 0. +expect_r9= overrides the ModDesc value.
    localparam [31:0] EXPECT_R9_DEFAULT = 32'h00000008;
    localparam [39:0] EXPECT_MASK = 40'hffffffffff;

    reg        rst_n;
    reg        cpu_reset;
    reg        cmd_en;
    reg        pclk;
    reg        fclk;
    reg        ck;

    wire        led, halted;
    wire [31:0] pc, r0, r1, r2, r3, r5, r9;
    wire [39:0] mask;
    wire [31:0] mem_addr, mem_wdata;
    wire        mem_write, mem_read;
    wire        phy_rd, phy_wr, phy_refresh;
    wire [25:0] phy_addr;
    wire [15:0] phy_din;
    wire [15:0] dout_unused;
    wire [127:0] dout128;
    wire        data_ready, busy;
    wire [7:0]  wstep, wstep1, wstep_run, wstep1_run;
    wire [1:0]  rclkpos;
    wire [2:0]  rclksel;
    wire        wlevel_done, rcalib_done;

    wire        rd_pin = cmd_en && (phy_rd === 1'b1);
    wire        wr_pin = cmd_en && (phy_wr === 1'b1);
    wire        ref_pin = cmd_en && (phy_refresh === 1'b1);
    // Silicon gives the CPU beat 0. SIM dout is a different slot.
    wire [15:0] beat0 = dout128[127:112];

    wire        ddr_nrst, ddr_ck, cke_ctl, cs_n, ras_n, cas_n, we_n, odt;
    wire        cke;
    assign #400 cke = cke_ctl;
    wire [2:0]  ba;
    wire [12:0] a;
    wire [1:0]  dm;
    wire [15:0] dq;
    wire [1:0]  dqs;
    wire [1:0]  dqs_n;
    wire [1:0]  tdqs_n;

    assign dqs_n[0] = (dqs[0] === 1'bz) ? 1'bz : ~dqs[0];
    assign dqs_n[1] = (dqs[1] === 1'bz) ? 1'bz : ~dqs[1];

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
        .rd(rd_pin),
        .wr(wr_pin),
        .refresh(ref_pin),
        .addr(phy_addr),
        .din(phy_din),
        .dout(dout_unused),
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

    CPUSimTop cpu (
        .clock(pclk),
        .reset(cpu_reset),
        .io_led(led),
        .io_pc(pc),
        .io_halted(halted),
        .io_r0(r0),
        .io_r1(r1),
        .io_r2(r2),
        .io_r3(r3),
        .io_r5(r5),
        .io_r9(r9),
        .io_mask(mask),
        .io_memAddr(mem_addr),
        .io_memWriteData(mem_wdata),
        .io_memWrite(mem_write),
        .io_memRead(mem_read),
        .phy_rd(phy_rd),
        .phy_wr(phy_wr),
        .phy_refresh(phy_refresh),
        .phy_addr(phy_addr),
        .phy_din(phy_din),
        .phy_dout(beat0),
        .phy_data_ready(data_ready),
        .phy_busy(busy),
        .phy_calib(rcalib_done)
    );

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

    integer waits, cycle, edges, max_cycles, cmds, reads;
    integer first_edge, prev_edge, period;
    reg [31:0] expect_r9;
    reg        prev_led;
    reg        saw_ready;
    reg [15:0] last_beat;
    reg [31:0] prev_pc;

    initial begin
        rst_n = 1'b0;
        cpu_reset = 1'b1;
        // phy_rd === 1'b1 already ignores X. Gating the command off
        // after reset release drops the bridge's one-cycle pulse.
        cmd_en = 1'b1;
        waits = 0;
        cycle = 0;
        edges = 0;
        cmds = 0;
        reads = 0;
        first_edge = -1;
        prev_edge = -1;
        period = -1;
        prev_led = 1'b0;
        saw_ready = 1'b0;
        last_beat = 16'hxxxx;
        prev_pc = 32'hxxxxxxxx;
        max_cycles = 500000;
        if (!$value$plusargs("max_pclk=%d", max_cycles))
            max_cycles = 500000;
        expect_r9 = EXPECT_R9_DEFAULT;
        if (!$value$plusargs("expect_r9=%h", expect_r9))
            expect_r9 = EXPECT_R9_DEFAULT;

        #10000;
        @(negedge ck);
        rst_n = 1'b1;
        if ($test$plusargs("cpu_now")) begin
            repeat (16) @(posedge pclk);
            cpu_reset = 1'b0;
        end

        if (!$test$plusargs("cpu_now")) while (rcalib_done !== 1'b1 && waits < PCLK_WAIT) begin
            @(posedge pclk);
            waits = waits + 1;
            if (waits == 1 || waits % 200 == 0) begin
                $display("WAIT cyc=%0d calib=%b wstep=%h/%h run=%h/%h",
                         waits, rcalib_done, wstep, wstep1, wstep_run, wstep1_run);
                $fflush;
            end
        end
        if (!$test$plusargs("cpu_now")) begin
            $display("CALIB done=%b wstep=%h/%h run=%h/%h rclkpos=%h rclksel=%h cycles=%0d",
                     rcalib_done, wstep, wstep1, wstep_run, wstep1_run,
                     rclkpos, rclksel, waits);
            $fflush;
            if (rcalib_done !== 1'b1) begin
                $display("PHY_SCORE fail");
                $finish;
            end
        end

        // Hold the CPU through training, then release it on pclk.
        repeat (16) @(posedge pclk);
        cpu_reset = 1'b0;
        #1;
        prev_led = led;
        $display("CPU reset released pc=%h pend=%b stall=%b rd=%b wr=%b ref=%b busy=%b",
                 pc, cpu.cpu.memoryAccessPending, cpu.cpu.io_memStall,
                 phy_rd, phy_wr, phy_refresh, busy);
        $fflush;

        while (edges < 2 && cycle < max_cycles) begin
            @(posedge pclk);
            #1;
            cycle = cycle + 1;
            if (data_ready === 1'b1 && !saw_ready) begin
                saw_ready = 1'b1;
                reads = reads + 1;
                last_beat = beat0;
                if (reads <= 8 || reads % 100 == 0) begin
                    $display("READ n=%0d pc=%h addr=%h beat0=%h r5=%h r9=%h mask=%h",
                             reads, pc, phy_addr, beat0, r5, r9, mask);
                    $fflush;
                end
            end
            if (data_ready !== 1'b1)
                saw_ready = 1'b0;
            if ((rd_pin || wr_pin || ref_pin) && !busy) begin
                cmds = cmds + 1;
            end
            if ($test$plusargs("cpu_trace") && pc !== prev_pc) begin
                $display("PC cyc=%0d pc=%h ir=%h r0=%h addr=%h pend=%b stall=%b",
                         cycle, pc, cpu.cpu._instructionRom_data, r0,
                         cpu.cpu.instructionRom.addr,
                         cpu.cpu.memoryAccessPending, cpu.cpu.io_memStall);
                $fflush;
                prev_pc = pc;
            end
            // Setup's link points at this halt. Reaching it before a
            // DRAM read means BT R0 did not enter the prologue.
            if (reads == 0 && pc[31:4] == 28'h000000b && cycle > 80) begin
                $display("END cycle=%0d edges=%0d first=%0d period=%0d pc=%h r5=%h r9=%h mask=%h reads=%0d",
                         cycle, edges, first_edge, period, pc, r5, r9, mask, reads);
                $display("PHY_SCORE fail");
                $finish;
            end
            if (led !== prev_led) begin
                if (first_edge < 0)
                    first_edge = cycle;
                else
                    period = cycle - prev_edge;
                prev_edge = cycle;
                edges = edges + 1;
                $display("LED cycle=%0d %b->%b pc=%h r5=%h r9=%h mask=%h",
                         cycle, prev_led, led, pc, r5, r9, mask);
                $fflush;
                prev_led = led;
            end
            if (cycle <= 20 || cycle % 200 == 0) begin
                $display("RUN cyc=%0d pc=%h r5=%h r9=%h mask=%h led=%b reads=%0d cmds=%0d",
                         cycle, pc, r5, r9, mask, led, reads, cmds);
                $fflush;
            end
        end

        $display("END cycle=%0d edges=%0d first=%0d period=%0d pc=%h r5=%h r9=%h mask=%h reads=%0d",
                 cycle, edges, first_edge, period, pc, r5, r9, mask, reads);
        if (edges >= 2 && period == EXPECT_PERIOD &&
            r5 === EXPECT_R5 && r9 === expect_r9 && mask === EXPECT_MASK)
            $display("PHY_SCORE pass");
        else
            $display("PHY_SCORE fail");
        $finish;
    end
endmodule
