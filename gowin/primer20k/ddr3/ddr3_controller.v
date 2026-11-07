
// Simple low-latency DDR3 PHY controller for Tang Primer 20K
// nand2mario, 2022.9
//
// Tested on SKHynix H5TQ1G63EFR-PBC (1Gb)
// - PB speed grade: JEDEC DDR3-1600 11-11-11 (aka DDR3-1600K)
// - RCD=RP=13.75ns, RC=48.75ns
// - Equivalent to "sg25" in Micron DDR3 model
//

// Undefine this to use DDR3-1066
`define DDR3_800

// `ifdef SIM shortcuts. They exist so Icarus can finish. They are
// not the silicon path, and a test that only watches `dout` under
// SIM is not a Dock result.
// - `dout` is dq_in[4]. DDR3_800 silicon uses dq_in[0].
// - dllstep is forced to 25 and dlllock is forced high. The DLL
//   primitive does not run.
// - The reset and CKE waits are 1 and 19 pclk ticks. ZQ stays at
//   512 pclk: the Micron model rejects later commands otherwise.
// - Write leveling starts at 8'h18 instead of 0.
// - Read calibration starts at rclkpos 1, rclksel 6, and commits
//   on rburst. It does not compare dq_in. In sim the first
//   rburst is the trailing edge, where dq_in[0] is X. The commit
//   then steps back one CK.
// - WLEVEL_COUNT and RCALIB_COUNT are 2.
// - dm_out is cleared with a nonblocking assign. A blocking
//   default is visible to OSER8_MEM on this same pclk, and the
//   write beat stays masked.

module ddr3_controller
#(
    // Main clock frequency, 75Mhz~100Mhz (DDR3 nominal clock 300Mhz~400Mhz)
    parameter         ROW_WIDTH = 13,
    parameter         COL_WIDTH = 10,
    parameter         BANK_WIDTH = 3,

    // Time delays in nCK (tCK=2.5ns for DDR-800, 1.875ns for DDR-1066).
`ifdef DDR3_800
    parameter CAS  = 6,     // 6 cycles, set in MR0[6,5,4,2] = 0100
    parameter BL   = 2,     // BC4 bursting means 2 cycles, MR0[1:0] = 10
    parameter CWL  = 5,     // 5 cycles, set in MR2[5:3] = 000
    parameter WR   = 6,     // 15ns, write recovery
    parameter MRD  = 8,     // 4 cycles, mode register set delay
    parameter RP   = 6,     // 13.75ns, precharge to active
    parameter RCD  = 6,     // 13.75ns, active to r/w
    parameter RC   = 20,    // 48.25ns, ref/active to ref/active
    parameter MOD  = 12     // 12nCK/15ns, cycles after MRS before any other command
`else
    // DDR3-1066
    parameter CAS  = 7,     // MR0[6,5,4,2] = 0110
    parameter CWL  = 6,     // MR2[5:3] = 001
    parameter RCD  = 8,     // 13.75ns, active to r/w
    parameter WR   = 8,     // MR0[11:9] = 100
    parameter MRD  = 8,     // >=4 cycles, mode register set delay
    parameter RP   = 8,     // 13.75ns, precharge to active
    parameter RC   = 26,    // 48.25ns, ref/active to ref/active
    parameter MOD  = 12     // 12nCK/15ns, cycles after MRS before any other command
`endif
)
(
    // DDR3 side interface
    inout [15:0]      DDR3_DQ,
    inout [1:0]       DDR3_DQS,
    output[ROW_WIDTH-1:0]  DDR3_A,
    output[BANK_WIDTH-1:0] DDR3_BA,

    output            DDR3_nRAS,
    output            DDR3_nCAS,
    output            DDR3_nWE,

    output            DDR3_nCS,     // always 0
    output            DDR3_CK,      // ck, 180-degree shifted fclk 
    output     reg    DDR3_CKE,     
    output            DDR3_nRESET,    // reset pin
    output     [1:0]  DDR3_DM,      // always 0
    output            DDR3_ODT,     // always 1
    
    // System side interface
    input             pclk,         // primary clock (rd, wr, etc), e.g. 100Mhz
    input             fclk,         // fast clock (4*pclk), e.g. 400Mhz
    input             ck,           // 90-degree shifted fclk for memory clock
    input             resetn,
    input             rd,           // command: read
    input             wr,           // command: write
    input             refresh,      // command: auto refresh. 4096 refresh cycles in 64ms. Once per 15us.
    input      [BANK_WIDTH+ROW_WIDTH+COL_WIDTH-1:0] 
                      addr,         // word address
    input      [15:0] din,          // 16-bit data input
    output    [15:0]  dout,         // word output
    output    [127:0] dout128,      // 128-bit data output
    output reg        data_ready = 1'b0,   // available 6 cycles after wr is set
    output reg        busy = 1'b1,  // 0: ready for next command

    // Write leveling. This is done after mode registers are set.
    output            write_level_done,  // 1 means write leveling is successful for this DQS
    output reg [7:0]  wstep,        // write-level result for DQS0
    output reg [7:0]  wstep1,       // write delay for DQS1
    output reg [7:0]  wstep_run,    // DQS0 delay actually used after calib
    output reg [7:0]  wstep1_run,   // DQS1 delay actually used after calib
    // After the eye locks, step_ov_en replaces that delay. The reader
    // sweep uses it. It stays low through write leveling and training.
    input      [7:0]  step0_ov,
    input      [7:0]  step1_ov,
    input             step_ov_en,

    // Read calibration
    // Increment rclkpos/rclksel, send a BL8 read command, and once a rburst
    // pulse is detected, then we have read calibration.
    output            read_calib_done,  // 1: read calibration successful
    output reg  [1:0] rclkpos,      // cycle value for read clock (0-3), 2 bits for each DQS
    output reg  [2:0] rclksel,      // phase value for read clock (0-7), 3 bits for each DQS
    
    output [63:0] debug
);

// More timing parameters
localparam WLMRD= 44;       // Write leveling wait time before DQS pulse
localparam SERDES = 16;     // SERDES round-trip latency in (OSER8 is 3 clk, IDER8 is 1 clk)

`ifdef DDR3_800
    localparam USEC = 100;  // a micro second in pclk cycles (pclk <= 100Mhz)
`else
    localparam USEC = 134;  // pclk <= 133Mhz
`endif

// Wait until DLL locked to do anything
wire dlllock;
wire rst_lock_n = resetn & dlllock;
reg resetn_delay;
assign DDR3_nRESET = rst_lock_n & resetn_delay;
assign DDR3_ODT = 1'b1;     // Use dynamic ODT

// Tri-state DQ inout signals (double DDR3_CK speed)
reg [15:0] dq_out [7:0];    // DQ output data
reg [0:3] dq_oen;           // out_enable_n for dq_out[1:0], [3:2], [5:4], [7:6]
wire [15:0] dq_in [7:0];    // DQ input data
reg [0:7] dqs_out;          // DQS output
reg [0:3] dqs_oen;          // out_enable_n for dqs_out[1:0], [3:2], [5:4], [7:6]
reg [0:7] dm_out;

// Bit lengths
typedef logic [7:0] BYTE;
typedef logic [3:0] NIB;
typedef logic [4:0] FIVEB;

// Debug stuff
reg [7:0] cnt_read = 0;
reg [7:0] cnt_write = 0;

// Output signals
reg nRAS[3:0], nCAS[3:0], nWE[3:0];
reg [ROW_WIDTH-1:0] A[3:0];
reg [2:0] BA[3:0];
assign DDR3_CK = ck;
assign DDR3_nCS = 1'b0;

assign dout128 = {dq_in[0], dq_in[1], dq_in[2], dq_in[3], dq_in[4], dq_in[5], dq_in[6], dq_in[7]};
`ifdef SIM
// SIM shortcut. DDR3_800 silicon uses dq_in[0], below.
assign dout = dq_in[4];
`else
    `ifdef DDR3_800
        assign dout = dq_in[0];
    `else
        assign dout = dq_in[4];
    `endif
`endif

// Our main FSM state
reg [3:0] state;                   
localparam RST_WAIT = 4'd0;
localparam CKE_WAIT = 4'b1;
localparam CONFIG = 4'd2;
localparam ZQCL = 4'd3;
localparam IDLE = 4'd4;
localparam READ = 4'd5;
localparam WRITE = 4'd6;
localparam REFRESH = 4'd7;
localparam WRITE_LEVELING = 4'd8;
localparam READ_CALIB = 4'd9;
reg [4:0] cycle;        // step within operation (config/read/write) 
reg tick;               // pulse after tick_counter cycles
reg [16:0] tick_counter = 17'd50_000;   

// RAS# CAS# WE#
localparam CMD_SetModeReg=3'b000;
localparam CMD_AutoRefresh=3'b001;
localparam CMD_PreCharge=3'b010;
localparam CMD_BankActivate=3'b011;
localparam CMD_Write=3'b100;
localparam CMD_Read=3'b101;
localparam CMD_ZQCL=3'b110;
localparam CMD_NOP=3'b111;

// Mode registers are {BA[2:0], A[12:0]}, total 16 bits
localparam [1:0] M_BL = 2'b01;      // burst length BC4 or 8 on the fly
`ifdef DDR3_800
localparam [3:0] M_CAS = 4'b0100;   // 6 cycles
localparam [2:0] M_CWL = 3'b000;    // 5 cycles
localparam [2:0] M_WR = 3'b010;     // 6 cycles
`else
localparam [3:0] M_CAS = 4'b0110;   // 7 cycles
localparam [2:0] M_CWL = 3'b001;    // 6 cycles
localparam [2:0] M_WR = 3'b100;     // 8 cycles
`endif
localparam M_DLLReset = 1'b1;
localparam M_RTT_NOM = 3'b000;      // Disabled, RTT_NOM is only needed for multi-rank systems
localparam M_RTT_WR = 2'b01;        // RTT_WR = 60ohm (2: 120ohm)
localparam M_RTT_WR_off = 2'b00;    //
localparam M_DRIVE = 2'b00;         // 00: low drive strength, 01: high
localparam M_AL = 2'b0;             // AL=0
wire [15:0] MR0 = 
//15 14 13 12    11 10 9   8           7     6 5 4       3     2         1 0
  {3'b000, 1'b0, M_WR,     M_DLLReset, 1'b0, M_CAS[3:1], 1'b0, M_CAS[0], M_BL};
wire [15:0] MR1 = 
//15 14 13 12:10 9             8 7   6             5           4 3   2             1           0   
  {3'b001, 3'b0, M_RTT_NOM[2], 2'b0, M_RTT_NOM[1], M_DRIVE[1], M_AL, M_RTT_NOM[0], M_DRIVE[0], 1'b0};
wire [15:0] MR2 =
//15 14 13 12 11 10 9          8 7 6 5 4 3  2 1 0
  {3'b010, 2'b0, M_RTT_WR_off, 3'b0, M_CWL, 3'b0};
wire [15:0] MR2_RTT_WR =        // Dynamic ODT is applied after write leveling
  {3'b010, 2'b0, M_RTT_WR,     3'b0, M_CWL, 3'b0};
// We use dynamic ODT because it allows ODT pin to be tied to 1. 
// RTT_WR will be automatically applied when there is a write.
// See: Micron TN-41-13: DDR3 Point-to-Point Design Support
wire [15:0] MR3 = {3'b011, 13'b0};

// Write leveling
reg wlevel_done = 1'b0;
reg [3:0] wlevel_cnt = 3'b0;
// The two byte lanes do not share a trace delay. One wstep left the
// earlier lane a data beat past its edge, so its byte landed on the
// neighbour column. Each lane stops on its own DQ feedback.
assign write_level_done = wlevel_done;

// Read calibration finds rburst. Training then scans offsets -4..+12
// from each lane's write-level edge. Offsets -4..-1 are the cliff.
// A row that also matches at the edge or above locks that window.
// A row that matches only on the cliff locks the cliff, which is the
// model eye. No fixed backoff.
reg [3:0] dqs_read = 4'b0;
reg dqs_hold = 1'b0;
reg wload_n = 1'b0;
wire [1:0] rburst;
reg [1:0] rburst_seen;
reg rcalib_done = 1'b0;
reg [3:0] rcalib_cnt = 4'b0;
assign read_calib_done = rcalib_done;

localparam [7:0] EYE_MAX = 8'd24;
localparam [2:0] E_SETTLE = 3'd0, E_WREQ = 3'd1, E_WBUSY = 3'd2,
                 E_RREQ = 3'd3, E_RBUSY = 3'd4, E_GAP = 3'd5,
                 E_MARK = 3'd6, E_STEP = 3'd7;
reg        eye_arm = 1'b0;
reg        eye_mode = 1'b0;
reg        eye_ran = 1'b0;
reg        eye_lock = 1'b0;
reg [7:0]  eye_lock0 = 8'd0, eye_lock1 = 8'd0;
reg [7:0]  eye_s0 = 8'd0, eye_s1 = 8'd0;
reg [7:0]  eye_edge0 = 8'd0, eye_edge1 = 8'd0;
reg [7:0]  eye_cen0 = 8'd0, eye_cen1 = 8'd0;
reg [2:0]  eye_st = E_SETTLE;
reg [1:0]  eye_ph = 2'd0;
reg [3:0]  eye_idx = 4'd0;
reg [7:0]  eye_bo = 8'd0;
reg [7:0]  eye_o0 = 8'd0;
reg [7:0]  best_row = 8'd0;
reg [4:0]  eye_wait = 5'd0;
reg [2:0]  eye_after = E_SETTLE;
reg        eye_bad = 1'b0;
reg        eye_saw_busy = 1'b0;
reg        eye_cap = 1'b0;
reg        eye_cap_clear = 1'b0;
reg [15:0] eye_got = 16'd0;
reg [15:0] eye_g0 = 16'd0, eye_g1 = 16'd0;
reg [15:0] eye_g0_edge = 16'd0;
reg [15:0] eye_g0_rdy = 16'd0;
reg        eye_pass = 1'b0;
// Stuck after training so the UART can show why calib stayed low.
// E0 is pattern 0 at the write-level edge, sampled with eye_got.
// ER is that same beat sampled while data_ready is high.
// EL is pattern 0 of the last trial. F is {pass, bad, lock, rclkpos, rclksel}.
assign debug = {eye_g0_edge, eye_g0, eye_cen0, eye_cen1, eye_bo,
                eye_pass, eye_bad, eye_lock, rclkpos, rclksel};
// The cycle data_ready is high is the beat the CPU uses.
always @(posedge pclk) begin
    if (~rst_lock_n)
        eye_g0_rdy <= 16'd0;
    else if (eye_mode && data_ready && eye_o0 == 8'd0
             && eye_bo == 8'd0 && eye_idx == 4'd0)
        eye_g0_rdy <= dq_in[0];
end
reg [25:0] eye_addr = 26'd0;
reg [15:0] eye_din = 16'd0;
reg        eye_pulse_rd = 1'b0, eye_pulse_wr = 1'b0, eye_commit = 1'b0;
reg        in_run = 1'b0, have = 1'b0;
reg [7:0]  run_lo = 8'd0, run_hi = 8'd0, best_lo = 8'd0, best_w = 8'd0;
reg signed [3:0] box_dx = -4'sd2, box_dy = -4'sd2;
reg        cliff_run = 1'b0, have_cliff = 1'b0;
reg [7:0]  cliff_lo = 8'd0, cliff_hi = 8'd0, cliff_cen = 8'd0;

wire [25:0] cmd_addr = eye_mode ? eye_addr : addr;
wire [15:0] cmd_din  = eye_mode ? eye_din  : din;
wire        do_rd = eye_mode ? eye_pulse_rd : rd;
wire        do_wr = eye_mode ? eye_pulse_wr : wr;

function [15:0] eye_pattern;
    input [2:0] i;
    begin
        case (i)
            3'd0: eye_pattern = 16'hA55A;
            3'd1: eye_pattern = 16'h5AA5;
            3'd2: eye_pattern = 16'hFF00;
            3'd3: eye_pattern = 16'h00FF;
            3'd4: eye_pattern = 16'h0F0F;
            3'd5: eye_pattern = 16'hF0F0;
            3'd6: eye_pattern = 16'h8001;
            default: eye_pattern = 16'h7FFE;
        endcase
    end
endfunction

// Index 0..EYE_LAST is the write-level edge plus an offset of -4..+12.
// The leveling edge is the first code that sees the DQS pulse, so the
// data eye is that code and the ones after it. Index 4 is offset 0.
// Indices 0..3 are the downward cliff: silicon read A500 there (high
// byte right, low byte zero). Stopping at the first three matches
// locks that cliff when it false-passes (Dock steps 0007/0009,
// C1 01, BO 02) and a later store comes back with its high byte
// replaced. Silicon keeps that row open until three matches at the
// edge or above lock. Only a row with no such match locks the cliff.
// The Micron model slips if a write lands on its edge, so sim keeps
// the first three matches unless +eye_decide.
localparam [7:0] EYE_LAST = 8'd16; // offsets -4 .. +12
function [7:0] eye_at;
    input [7:0] edge_c;
    input [7:0] idx;
    integer sum;
    begin
        sum = edge_c;
        sum = sum + idx;
        sum = sum - 4;
        if (sum < 0)
            eye_at = 8'd0;
        else if (sum > 255)
            eye_at = 8'd255;
        else
            eye_at = sum[7:0];
    end
endfunction

function eye_hit;
    input [1:0] ph;
    input [15:0] got;
    input [15:0] expd;
    begin
        if (ph == 2'd0)
            eye_hit = (got[7:0] === expd[7:0]);
        else if (ph == 2'd1)
            eye_hit = (got[15:8] === expd[15:8]);
        else
            eye_hit = (got === expd);
    end
endfunction

function [7:0] eye_add;
    input [7:0] base;
    input signed [3:0] delta;
    integer sum;
    begin
        sum = base;
        sum = sum + delta;
        if (sum < 0)
            eye_add = 8'd0;
        else if (sum > EYE_MAX)
            eye_add = EYE_MAX;
        else
            eye_add = sum[7:0];
    end
endfunction

always @(posedge pclk) begin
    if (~rst_lock_n) begin
        wstep_run <= 8'd0;
        wstep1_run <= 8'd0;
    // The reader sweep replaces the trained delay after calib.
    end else if (rcalib_done && step_ov_en) begin
        wstep_run <= step0_ov;
        wstep1_run <= step1_ov;
    end else if (eye_mode) begin
        wstep_run <= eye_s0;
        wstep1_run <= eye_s1;
    end else if (eye_lock) begin
        wstep_run <= eye_lock0;
        wstep1_run <= eye_lock1;
    end else begin
        wstep_run <= wstep;
        wstep1_run <= wstep1;
    end
end

`ifdef SIM
localparam WLEVEL_COUNT=2;
localparam RCALIB_COUNT=2;
`else
localparam WLEVEL_COUNT=1;          // test this many times before a wstep passes write leveling
localparam RCALIB_COUNT=16;         // NESTang Dock: 16 confirmed rburst hits before commit
`endif

//
// DDR3 state machine
//
always @(posedge pclk) begin    
  if (rst_lock_n) begin
    cycle <= cycle == 5'd31 ? 5'd31 : cycle + 4'd1;
    tick <= tick_counter == 16'd1;
    tick_counter <= tick_counter == 0 ? 0 : tick_counter - 16'd1;

    // defaults
    {nRAS[0], nCAS[0], nWE[0]} <= CMD_NOP; {nRAS[1], nCAS[1], nWE[1]} <= CMD_NOP;
    {nRAS[2], nCAS[2], nWE[2]} <= CMD_NOP; {nRAS[3], nCAS[3], nWE[3]} <= CMD_NOP;
    A[0] <= 1'b0; A[1] <= 1'b0; A[2] <= 1'b0; A[3] <= 1'b0;
    BA[0] <= 3'b0; BA[1] <= 3'b0; BA[2] <= 3'b0; BA[3] <= 3'b0;
    // Nonblocking, same as dq_oen. A blocking default here is
    // already 8'hff when OSER8_MEM samples DM on this pclk, so
    // the unmask scheduled below never reaches the pins.
    dm_out <= 8'b1111_1111;
    dqs_oen[0:3] <= 4'b1111;
    dq_oen[0:3] <= 4'b1111;
    dqs_hold <= 1'b0;
    wload_n <= 1'b0;
    if (eye_cap_clear)
        eye_cap <= 1'b0;

    casex ({state, cycle})
        // RESET off after 200 us 
        {RST_WAIT, 5'bxxxxx} : if (tick) begin
            resetn_delay <= 1'b1;
`ifdef SIM
            // SIM shortcut. Silicon waits 500 us.
            tick_counter <= 17'd19;
`else
            tick_counter <= 500 * USEC + 20;
`endif
            state <= CKE_WAIT;
        end
        
        // CKE on after 500 us before 
        {CKE_WAIT, 5'bxxxxx} : begin
            if (tick_counter == 16'd15)
                DDR3_CKE <= 1'b1;       // tXPR (120ns) between CKE and MRS
            if (tick) begin
                state <= CONFIG;
                cycle <= 0;
            end
        end

        // Mode Register Config sequence
        //  cycle  //0 \___/ ...___//4 \___/ ... __//8 \___/ ...___//12\___/ ...___//16\___/ ...___//28\___/ ...___/1024+28\___
        //  cmd                    |  MR0  |       |  MR1  |       |  MR2  |       |  MR3  |       | ZQCL  |       | _Next_|
        //                         '---- MRD=4 ----'----  MRD=4 ---'----  MRD=4 ---'-----MOD=12----'--tZQCL+tDLLK--'
        {CONFIG, FIVEB'(0)} : begin
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_SetModeReg;
            {BA[0], A[0][12:0]} <= MR2;
        end
        {CONFIG, FIVEB'(MRD/4)} : begin
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_SetModeReg;
            {BA[0], A[0][12:0]} <= MR3;
        end
        {CONFIG, FIVEB'(MRD/2)} : begin
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_SetModeReg;
            {BA[0], A[0][12:0]} <= MR1;
        end
        {CONFIG, FIVEB'(MRD*3/4)} : begin
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_SetModeReg;
            {BA[0], A[0][12:0]} <= MR0;
        end
        {CONFIG, FIVEB'(MRD*3/4+MOD/4+1)} : begin
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_ZQCL;
            A[0][10] <= 1'b1;         // long ZQ calibration
`ifdef SIM
            // Not shortened. tZQinit is 512 nCK and the Micron model
            // rejects the next ACT if this wait is the old 2 ticks.
            tick_counter <= 16'd512 + 16'd2;
`else
            tick_counter <= 16'd512 + 2;
`endif
            state <= ZQCL;
        end

        // ZQ calibration
        {ZQCL, 5'bxxxxx} : if (tick) begin
            state <= WRITE_LEVELING;
            cycle <= 0;
        end

        // read/write/refresh
        {IDLE, 5'bxxxxx}: if (eye_commit) begin
            rcalib_done <= 1'b1;
            busy <= 1'b0;
            $display("All initialization DONE... eye %0d/%0d", eye_lock0, eye_lock1);
        end else if (do_rd || do_wr) begin
            // bank activate
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_BankActivate;
            BA[0] <= cmd_addr[ROW_WIDTH+COL_WIDTH+BANK_WIDTH-1 : ROW_WIDTH+COL_WIDTH];    // bank id
            A[0] <= cmd_addr[ROW_WIDTH+COL_WIDTH-1:COL_WIDTH];      // 12-bit row address
            state <= do_rd ? READ : WRITE;
            if (do_rd) cnt_read <= cnt_read == 8'hff ? 8'hff : cnt_read + 1;
            if (do_wr) cnt_write <= cnt_write == 8'hff ? 8'hff : cnt_write + 1;
            cycle <= 4'd1;
            busy <= 1'b1;
            // HOLD resets the read FIFO. Without it, odd columns come
            // back as the even one and the prologue compare fails.
            // It also stops the write clock (UG286). The reload below
            // puts that clock back on WSTEP before the next store.
            if (do_rd) dqs_hold <= 1'b1;
        end else if (!eye_mode && refresh) begin
            // auto-refresh
            // no need for precharge-all b/c all our r/w are done with auto-precharge.
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_AutoRefresh;
            state <= REFRESH;
            cycle <= 4'd1;
            busy <= 1'b1;
        end

        // Read sequence (9 cycles at 100Mhz)
        // Quirk: you can issue next command once you see data_ready at cycle 8 (busy will be 0 next cycle), that saves a cycle
// CK    \___//0 \___/ 1 \___/ 2 \___/ 3 \___//4 \___/ 5 \___/ 6 \___/ 7 \___//8 \___/ 9 \___/ 10\___/ 11 ...//32\___/ 33\___/ 34\___/ 35\___//36\___/ 37\___/ 38\___/ 39\___
// RD   _||              1               ||                                                                                              ||           _NEXT_         |
// CMD                                   ||ACTIVE|       |       |       ||      |       | READ  |       ||
// ADDR                                  ||Row   |       |       |       ||      |       | Col n |       ||
// DQS  ---------------------------------------------------------------------------------------------____/   \___/   \___--------------
// DQ                                                                                                    ||DO|DO |DO |DO ||
//                                                                                                       ||n |n+1|n+2|n+3||
//                                       `-------------------- RCD=6 --------------------' CL6+SERDES=22 '
// data_ready ___________________________________________________________________________________________/                               \______
// busy  ________________________________/                                                                                               \______
        {READ, FIVEB'(RCD/4)}: begin              // 1       
            {nRAS[RCD%4], nCAS[RCD%4], nWE[RCD%4]} <= CMD_Read;     // 101
            BA[RCD%4] <= cmd_addr[ROW_WIDTH+COL_WIDTH+BANK_WIDTH-1 : ROW_WIDTH+COL_WIDTH];    // bank id
            A[RCD%4][12] <= 1'b1;                   // BL8 burst length
            A[RCD%4][10] <= 1'b1;                   // set auto precharge
            A[RCD%4][9:0] <= cmd_addr[COL_WIDTH-1:0];   // column address
            dqs_hold <= 1'b1;                   // one cycle longer, setup
        end
        {READ, FIVEB'((RCD+CAS+SERDES)/4+1)}: begin   // 7 (6+6+16 = 28)
            data_ready <= 1'b1;
        end
        {READ, FIVEB'((RCD+CAS+SERDES)/4+2)}: begin // 8
            data_ready <= 1'b0;
            busy <= 0;
            state <= IDLE;
            // dq_in is registered on the same edge that raises
            // data_ready. This block still sees the previous beat
            // on that edge. The CPU sees the new beat once
            // data_ready is high, which is this edge.
            if (eye_mode) begin
                eye_got <= dq_in[0];
                eye_cap <= 1'b1;
            end
            // WLOADN low reloads the write delay from WSTEP. HOLD left
            // it stopped. A one-cycle high here makes the falling edge
            // that loads WSTEP again before the bridge's next command.
            wload_n <= 1'b1;
        end

        // write sequence (7 cycles at 100Mhz)
// CK     \___//0 \___/ 1 \___/ 2 \___/ 3 \___//4 \___/ 5 \___/ 6 \___/ 7 \___//8 \___/ 9 \___/ 10\___/ 11\___//12\___/ 13\___/ 14\___/ 15\___//16\___/ 17\___/ 18\___/ 19 ...//28\___/ 29\___/ 30\___/ 31\___
// WR     |               1               ||                                                                                          |   ||  |   |                       ||           _NEXT_
// CMD                                    ||ACTIVE|       |       |       ||      |       | WRITE |       ||                          |   ||  |   |
// ADDR                                   || Row  |       |       |       ||      |       | COL n |       ||                          |   ||  |   |
// DQS  ----------------------------------------------------------------------------------------------------------------------/   \___/   \___/   \___----------
// DQ                                                                                                                               |Din|Din|Din|Din|Din|Din|Din|Din|
//                                                                                                                                  |n  |n+1|n+2|n+3|n+4|n+5|n+6|n+7|
//                                            `-------------------- RCD=6 --------------------'--------------- CWL = 5 ---------------'------------  4  --------------'--------- WR+RP = 12 ----------'
// busy __________________________________/                                                                                                                           \_______ (negedge at 24)

        {WRITE, FIVEB'(RCD/4)}: begin             
            {nRAS[RCD%4], nCAS[RCD%4], nWE[RCD%4]} <= CMD_Write;    // 100
            BA[RCD%4] <= cmd_addr[ROW_WIDTH+COL_WIDTH+BANK_WIDTH-1 : ROW_WIDTH+COL_WIDTH];    // bank id
            A[RCD%4][10] <= 1'b1;                           // set auto precharge
            A[RCD%4][9:0] <= cmd_addr[COL_WIDTH-1:0];           // column address
            A[RCD%4][12] <= 1'b0;                           // BC4 burst length
        end
`ifdef DDR3_800
        {WRITE, FIVEB'((RCD+CWL)/4)}: begin
            // DQS output
            dqs_out <= 8'b1111_1110;
            dqs_oen <= 4'b1110;

            // DQ output
            dq_out[6] <= 0; dq_out[7] <= cmd_din;
            dq_oen <= 4'b1110;

            // DM, umask the word we are writing to
            // Note that BC4 write always start from whole 4 words (not the exact address we want to write to)
            dm_out[7] <= !(cmd_addr[1:0] == 2'b00);
        end
        {WRITE, FIVEB'((RCD+CWL)/4+1)}: begin
            // DQS output
            dqs_out <= 8'b1010_0000;
            dqs_oen <= 4'b0011;

            // DQ output
            dq_out[0] <= cmd_din; dq_out[1] <= cmd_din;
            dq_out[2] <= cmd_din; dq_out[3] <= 0;
            dq_oen <= 4'b0011;

            dm_out[0] <= !(cmd_addr[1:0] == 2'b01);
            dm_out[1] <= !(cmd_addr[1:0] == 2'b10);
            dm_out[2] <= !(cmd_addr[1:0] == 2'b11);
        end
        {WRITE, FIVEB'(20/4)}: begin            // busy=0 at 24
            busy <= 0;
            state <= IDLE;
        end
`else
    // DDR3-1066: phase is 2 steps ahead of DDR3-800
        {WRITE, FIVEB'((RCD+CWL)/4)}: begin         // 3 (8+6=14) for DDR3-1066
            // DQS output
            dqs_out <= 8'b1111_1010;
            dqs_oen <= 4'b1100;

            // DQ output
            dq_out[4] <= 0; dq_out[5] <= cmd_din;
            dq_out[6] <= cmd_din; dq_out[7] <= cmd_din;
            dq_oen <= 4'b1100;

            dm_out[5] <= !(cmd_addr[1:0] == 2'b00);
            dm_out[6] <= !(cmd_addr[1:0] == 2'b01);
            dm_out[7] <= !(cmd_addr[1:0] == 2'b10);
        end
        {WRITE, FIVEB'((RCD+CWL)/4+1)}: begin
            // DQS output
            dqs_out <= 8'b1000_0000;
            dqs_oen <= 4'b0111;

            // DQ output
            dq_out[0] <= cmd_din; dq_out[1] <= 0;
            dq_oen <= 4'b0111;

            dm_out[0] <= !(cmd_addr[1:0] == 2'b11);
        end
        {WRITE, FIVEB'(24/4)}: begin              // busy=0 at 28
            busy <= 0;
            state <= IDLE;
        end
`endif


        // refresh sequence (6 cycles in 100Mhz)
// ck      \___//0 \___/ 1 \___/ 2 \___/ 3 \___//4 \___/ 5 \___/ 6 \___/ 7  ...//20\___/ 21\___/ 22\___/ 23\___//24\___/ 25\___/ 26\___/ 27\___
// refresh |               1               |                                                               ||            _NEXT_            |
// cmd                                     |Refresh|       |       |       ||      |       |       |       ||
// busy     _______________________________/                               \________________________________
//                                         `----------------------- T_RC ----------------------------------'
        {REFRESH, FIVEB'(RC/4)}: begin
            state <= IDLE;
            busy <= 0;
        end

        // Write Leveling
        // After tWLDQSEN(25nck), drive DQS low. After tWLMRD (40nCK), pulse DQS, then after tWLO (7.2ns) feedback is provide on prime DQ
        {WRITE_LEVELING, FIVEB'(0)}: begin
            $display("Entering WRITE LEVELING");
            // enter write leveling mode
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_SetModeReg;
            // MR1[9,6,2]=001, RTT_NOM=60ohm, as dynamic ODT is not available in write leveling
            {BA[0], A[0][12:0]} <= MR1 | 8'b1000_0100;      // MR1[7] is write-leveling                    
            wlevel_cnt <= 0;
`ifdef SIM
    `ifdef DDR3_800
            // SIM shortcut. Silicon starts the search at 0.
            wstep <= 8'h18;
            wstep1 <= 8'h18;
    `else
            wstep <= 8'h12;
            wstep1 <= 8'h12;
    `endif
`endif
        end
        {WRITE_LEVELING, FIVEB'(WLMRD/4-1)}, {WRITE_LEVELING, FIVEB'(WLMRD/4+1)},
        {WRITE_LEVELING, FIVEB'(WLMRD/4+2)}, {WRITE_LEVELING, FIVEB'(WLMRD/4+3)},
        {WRITE_LEVELING, FIVEB'(WLMRD/4+4)}, {WRITE_LEVELING, FIVEB'(WLMRD/4+5)}: begin
            dqs_out[0:7] <= 8'b0;               // bring down DQS
            dqs_oen[0:3] <= 4'b0;
        end
        {WRITE_LEVELING, FIVEB'(WLMRD/4)}: begin
            $display("wstep=%d", wstep);
            dqs_out[0:7] <= 8'b1010_1010;       // provide a test pulse
            dqs_oen[0:3] <= 4'b0;                    
        end
        {WRITE_LEVELING, FIVEB'(WLMRD/4+6)}: begin             // SERDES round trip + feedback time tWLO=7.5ns
            dqs_out[0:7] <= 8'b0;
            dqs_oen[0:3] <= 4'b0;

            // X or Z is not a high. On the board DQ is 0 or 1, so
            // this is the same test. An undriven sim DQ used to
            // fall through (~X is X, and an if on X does not fire)
            // and write leveling reported done.
            $display("WL sample dq0=%b dq8=%b wstep=%0d wstep1=%0d",
                     DDR3_DQ[0], DDR3_DQ[8], wstep, wstep1);
            if (DDR3_DQ[0] !== 1'b1 || DDR3_DQ[8] !== 1'b1) begin
                if (DDR3_DQ[0] !== 1'b1)
                    wstep <= wstep + 1'd1;
                if (DDR3_DQ[8] !== 1'b1)
                    wstep1 <= wstep1 + 1'd1;
                wlevel_cnt <= 0;
                cycle <= FIVEB'(WLMRD/4-1);    // loop
            end else begin
                wlevel_cnt <= wlevel_cnt + 1'b1;
                // test WLEVEL_COUNT times before we commit
                if (wlevel_cnt == NIB'(WLEVEL_COUNT-1'b1)) begin
                    $display("Write leveling process finished.");
                    wlevel_done <= 1'b1;
                    // Exit write leveling mode
                    {nRAS[0], nCAS[0], nWE[0]} <= CMD_SetModeReg;
                    {BA[0], A[0][12:0]} <= MR1;      // A[7] is write-leveling
                end else
                    cycle <= FIVEB'(WLMRD/4-1);
            end     
        end
        {WRITE_LEVELING, FIVEB'((WLMRD+MRD)/4+6)}: begin
            // Turn on dynamic ODT
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_SetModeReg;
            {BA[0], A[0][12:0]} <= MR2_RTT_WR;
        end
        {WRITE_LEVELING, FIVEB'((WLMRD+MRD+MOD)/4+6)}: begin
            state <= READ_CALIB;                // now continue to read calibration
            cycle <= 0;
        end

        // Read calibration
        // Issues BL8 read commands while adjusting rclkpos (0-3), rclksel (0-7)
        // until we see rburst pulse after the read. Then read calibration is achieved.
        {READ_CALIB, FIVEB'(0)}: begin
            $display("Entering READ CALIBRATION");
            // activate bank 0
            {nRAS[0], nCAS[0], nWE[0]} <= CMD_BankActivate;
            BA[0] <= 0; A[0] <= 0;
            rcalib_cnt <= 0;
`ifdef SIM
            // SIM shortcut. A starting guess, not a measured eye.
            // The search still commits on rburst, not on dq_in.
    `ifdef DDR3_800
            rclkpos <= 2'd1; rclksel <= 3'd6;
    `else
            rclkpos <= 2'd1; rclksel <= 3'd0;
    `endif
`endif
        end
        {READ_CALIB, FIVEB'(RCD/4)}: begin
            // issue read
            $display("rclkpos=%d, rclksel=%d", rclkpos, rclksel);
            {nRAS[2], nCAS[2], nWE[2]} <= CMD_Read;
            A[2][12] <= 1'b1;                   // BL8 burst length
            A[2][10] <= 1'b0;                   // NO auto precharge
            A[2][9:0] <= 0;                     // row address=0
        end
        {READ_CALIB, FIVEB'(RCD/4+10)}: begin   // Allow 10 cycles for rburst signal
            if (rburst_seen != 2'b11) begin
                rclksel <= rclksel + 3'b1;
                rclkpos <= rclksel == 3'd7 ? rclkpos + 2'b1 : rclkpos;
                rcalib_cnt <= 0;
                cycle <= FIVEB'(RCD/4);         // loop
            end else begin
                rcalib_cnt <= rcalib_cnt + 1'b1;
                // test RCALIB_COUNT times before we commit
                if (rcalib_cnt == NIB'(RCALIB_COUNT - 1)) begin
                    // Read gate only. rcalib_done waits for the eye.
`ifdef SIM
                    // SIM shortcut. The first rburst is the trailing
                    // edge of the strobe: dq_in[0] is X there, and the
                    // written word is one CK (4 steps of 1/4 CK)
                    // earlier. Silicon commits on the rburst it found.
                    if (rclksel >= 3'd4)
                        rclksel <= rclksel - 3'd4;
                    else begin
                        rclksel <= rclksel + 3'd4;
                        rclkpos <= rclkpos - 2'd1;
                    end
`endif
                    {nRAS[0], nCAS[0], nWE[0]} <= CMD_PreCharge;    // precharge
                    BA[0] <= 0; A[0] <= 0;                          // bank 0, row 0
                    eye_arm <= 1'b1;
                end else 
                    cycle <= FIVEB'(RCD/4);     // loop
            end
        end
        {READ_CALIB, FIVEB'(RCD/4+10+RP/4)}: begin
            // Precharge is finished. The eye trainer issues the first
            // command from IDLE. The CPU stays reset until it locks.
            $display("Read gate found. Training the write eye.");
            busy <= 1'b1;
            state <= IDLE;
        end
    endcase
  end else if (~rst_lock_n) begin
        busy <= 1'b1;
        data_ready <= 1'b0;
        DDR3_CKE <= 1'b0;
       {nRAS[0], nCAS[0], nWE[0]} <= CMD_NOP;
       {nRAS[1], nCAS[1], nWE[1]} <= CMD_NOP;
       {nRAS[2], nCAS[2], nWE[2]} <= CMD_NOP;
       {nRAS[3], nCAS[3], nWE[3]} <= CMD_NOP;
`ifdef SIM
        // SIM shortcut. Silicon waits 60000 pclk before releasing reset.
        tick_counter <= 16'd1;
`else
        tick_counter <= 16'd60_000;     // initial 500us delay
`endif
        tick <= 0;
        cycle <= 0;
        wlevel_cnt <= 0; wlevel_done <= 2'b0; wstep <= 0; wstep1 <= 0;
        wload_n <= 1'b0; dqs_hold <= 1'b0;
        rcalib_cnt <= 0; rcalib_done <= 0; rclkpos <= 0; rclksel <= 0;
        eye_arm <= 1'b0;
        eye_cap <= 1'b0;
        resetn_delay <= 1'b0;       // cause extra 200us reset for DDR3
        // Serializer inputs power up X. An X beat with DM low
        // stores X, and the read gives that X back.
        dq_out[0] <= 16'd0; dq_out[1] <= 16'd0; dq_out[2] <= 16'd0; dq_out[3] <= 16'd0;
        dq_out[4] <= 16'd0; dq_out[5] <= 16'd0; dq_out[6] <= 16'd0; dq_out[7] <= 16'd0;
        dqs_out <= 8'd0;
        dm_out <= 8'd0;
        state <= RST_WAIT;
  end
end

// Write-eye trainer. Runs once the read gate has precharged, before
// read_calib_done. Eight halfwords cover every DQ bit, the neighbour
// column, and the two bytes. A sample counts when the whole word
// matches in dq_in[0]. The inner scan finishes the lane-0 row.
// Three matches at or above the write-level edge lock that center.
// If the row never matches there, three cliff matches lock instead.
// No match on any row leaves calib low.
// The window math is an 8-bit subtract. Doing it in blocking locals
// inside the clocked block missed pclk by about 1.5 ns.
wire [7:0] span_lo = in_run ? run_lo : eye_bo;
wire [7:0] span_w  = eye_bo - span_lo + 8'd1;
wire [7:0] close_w = (run_hi >= run_lo) ? (run_hi - run_lo + 8'd1) : 8'd1;
wire       span_wider = !have || (span_w >= best_w);
wire       close_wider = !have || (close_w >= best_w);
// Lane 1 is the inner sweep. EYE_LAST is the last offset index.
wire       inner_end = (eye_bo >= EYE_LAST);
wire       outer_end = (eye_o0 >= EYE_LAST);
// Index 4 is the write-level edge. 0..3 are the cliff.
wire       eye_above = (eye_bo >= 8'd4);
wire [7:0] cliff_w = cliff_hi - cliff_lo + 8'd1;
// Three matches at or above the edge end the row. A cliff match
// does not, and neither does a miss: the rest of this row can
// still hold the data eye.
// The Micron model passes only below its write-level edge, and a
// normal write on that edge slips the sim strobe. Sim therefore
// keeps the first three matches. Silicon, and +eye_decide, do not
// lock that cliff when the same row has a later window.
`ifdef SIM
reg silicon_eye = 1'b0;
initial silicon_eye = $test$plusargs("eye_decide");
`else
wire silicon_eye = 1'b1;
`endif
wire       eye_close = (!eye_bad && span_w >= 8'd3 && (eye_above || !silicon_eye))
                    || (eye_bad && in_run && !silicon_eye);
always @(posedge pclk) begin
    eye_pulse_rd <= 1'b0;
    eye_pulse_wr <= 1'b0;
    eye_commit <= 1'b0;
    eye_cap_clear <= 1'b0;
    if (~rst_lock_n) begin
        eye_mode <= 1'b0;
        eye_ran <= 1'b0;
        eye_lock <= 1'b0;
        eye_lock0 <= 8'd0;
        eye_lock1 <= 8'd0;
        eye_st <= E_SETTLE;
        eye_ph <= 2'd0;
        eye_idx <= 4'd0;
        eye_bo <= 8'd0;
        eye_o0 <= 8'd0;
        best_row <= 8'd0;
        eye_wait <= 5'd0;
        eye_bad <= 1'b0;
        eye_pass <= 1'b0;
        eye_g0_edge <= 16'd0;
        eye_saw_busy <= 1'b0;
        in_run <= 1'b0;
        have <= 1'b0;
        best_w <= 8'd0;
        box_dx <= -4'sd2;
        box_dy <= -4'sd2;
        cliff_run <= 1'b0;
        have_cliff <= 1'b0;
        cliff_lo <= 8'd0;
        cliff_hi <= 8'd0;
        cliff_cen <= 8'd0;
    end else if (!eye_ran && eye_arm && state == IDLE) begin
        eye_ran <= 1'b1;
        eye_mode <= 1'b1;
        eye_lock <= 1'b0;
        eye_edge0 <= wstep;
        eye_edge1 <= wstep1;
        eye_s0 <= wstep;
        eye_s1 <= wstep1;
        eye_ph <= 2'd0;
        eye_bo <= 8'd0;
        eye_st <= E_SETTLE;
        eye_wait <= 5'd0;
        in_run <= 1'b0;
        have <= 1'b0;
        best_w <= 8'd0;
        cliff_run <= 1'b0;
        have_cliff <= 1'b0;
        $display("EYE edges %0d/%0d", wstep, wstep1);
        $fflush();
    end else if (eye_mode) begin
        case (eye_st)
            E_SETTLE: begin
                // Both lanes move. A byte can match while the other
                // lane is still on the write-level edge, and that
                // pair is not a joint full-word eye.
                eye_s0 <= eye_at(eye_edge0, eye_o0);
                eye_s1 <= eye_at(eye_edge1, eye_bo);
                if (eye_wait == 5'd16) begin
                    eye_wait <= 5'd0;
                    eye_idx <= 4'd0;
                    eye_bad <= 1'b0;
                    eye_st <= E_WREQ;
                end else
                    eye_wait <= eye_wait + 5'd1;
            end
            E_WREQ: begin
                eye_addr <= {22'd0, eye_idx};
                eye_din <= eye_pattern(eye_idx[2:0]);
                eye_pulse_wr <= 1'b1;
                eye_saw_busy <= 1'b0;
                eye_st <= E_WBUSY;
            end
            E_WBUSY: begin
                if (busy)
                    eye_saw_busy <= 1'b1;
                if (eye_saw_busy && !busy && state == IDLE) begin
                    eye_saw_busy <= 1'b0;
                    eye_wait <= 5'd0;
                    if (eye_idx == 4'd7) begin
                        eye_idx <= 4'd0;
                        eye_after <= E_RREQ;
                    end else begin
                        eye_idx <= eye_idx + 4'd1;
                        eye_after <= E_WREQ;
                    end
                    eye_st <= E_GAP;
                end
            end
            E_RREQ: begin
                eye_addr <= {22'd0, eye_idx};
                eye_cap_clear <= 1'b1;
                eye_pulse_rd <= 1'b1;
                eye_saw_busy <= 1'b0;
                eye_st <= E_RBUSY;
            end
            E_RBUSY: begin
                if (busy)
                    eye_saw_busy <= 1'b1;
                if (eye_saw_busy && !busy && state == IDLE) begin
                    eye_saw_busy <= 1'b0;
                    if (eye_cap !== 1'b1 || !eye_hit(2'd2, eye_got, eye_pattern(eye_idx[2:0])))
                        eye_bad <= 1'b1;
                    if (eye_idx == 4'd0) begin
                        eye_g0 <= eye_got;
                        if (eye_o0 == 8'd0 && eye_bo == 8'd0)
                            eye_g0_edge <= eye_got;
                    end
                    if (eye_idx == 4'd1)
                        eye_g1 <= eye_got;
                    eye_wait <= 5'd0;
                    if (eye_idx == 4'd7) begin
`ifdef SIM
                        // +eye_decide plants a cliff at 0..2 and a real
                        // window at 5..7 on lane 0's first row. The lock
                        // has to be the real window.
                        if ($test$plusargs("eye_decide")) begin
                            if (eye_o0 == 8'd0 && (eye_bo <= 8'd2
                                    || (eye_bo >= 8'd5 && eye_bo <= 8'd7)))
                                eye_bad <= 1'b0;
                            else
                                eye_bad <= 1'b1;
                        end
`endif
                        eye_after <= E_MARK;
                    end else begin
                        eye_idx <= eye_idx + 4'd1;
                        eye_after <= E_RREQ;
                    end
                    eye_st <= E_GAP;
                end
            end
            E_GAP: begin
                if (eye_wait == 5'd16) begin
                    eye_wait <= 5'd0;
                    eye_st <= eye_after;
                end else
                    eye_wait <= eye_wait + 5'd1;
            end
            E_MARK: begin
                // A cliff run ends at the first miss or at the edge.
                // Its center is kept only as this row's fallback.
                if (cliff_run && (eye_bad || eye_above)) begin
                    cliff_run <= 1'b0;
                    if (!have_cliff && cliff_w >= 8'd3) begin
                        have_cliff <= 1'b1;
                        cliff_cen <= cliff_lo + 8'd1;
                    end
                end
                if (!eye_bad && !eye_above && silicon_eye) begin
                    eye_pass <= 1'b1;
                    if (!cliff_run)
                        cliff_lo <= eye_bo;
                    cliff_run <= 1'b1;
                    cliff_hi <= eye_bo;
                end else if (!eye_bad && (eye_above || !silicon_eye)) begin
                    eye_pass <= 1'b1;
                    if (!in_run)
                        run_lo <= eye_bo;
                    in_run <= 1'b1;
                    run_hi <= eye_bo;
                    if (span_wider) begin
                        have <= 1'b1;
                        best_lo <= span_lo;
                        best_w <= span_w;
                    end
                end else if (eye_bad && in_run) begin
                    in_run <= 1'b0;
                    if (close_wider) begin
                        have <= 1'b1;
                        best_lo <= run_lo;
                        best_w <= close_w;
                    end
                end
                $display("EYE o0=%0d bo=%0d s=%0d/%0d g0=%h g1=%h bad=%b",
                         eye_o0, eye_bo, eye_s0, eye_s1, eye_g0, eye_g1, eye_bad);
                $fflush();
                if (!inner_end && !eye_close) begin
                    eye_bo <= eye_bo + 8'd1;
                    eye_st <= E_SETTLE;
                end else
                    eye_st <= E_STEP;
            end
            E_STEP: begin
                // This row's window was registered on the previous cycle.
                if (have && best_w >= 8'd3) begin
                    eye_cen0 <= eye_o0;
                    eye_cen1 <= best_lo + (best_w >> 1);
                    eye_lock0 <= eye_at(eye_edge0, eye_o0);
                    eye_lock1 <= eye_at(eye_edge1, best_lo + (best_w >> 1));
                    eye_lock <= 1'b1;
                    eye_mode <= 1'b0;
                    eye_commit <= 1'b1;
                    $display("EYE pass %0d/%0d",
                             eye_at(eye_edge0, eye_o0),
                             eye_at(eye_edge1, best_lo + (best_w >> 1)));
                    $fflush();
                end else if (have_cliff) begin
                    eye_cen0 <= eye_o0;
                    eye_cen1 <= cliff_cen;
                    eye_lock0 <= eye_at(eye_edge0, eye_o0);
                    eye_lock1 <= eye_at(eye_edge1, cliff_cen);
                    eye_lock <= 1'b1;
                    eye_mode <= 1'b0;
                    eye_commit <= 1'b1;
                    $display("EYE pass %0d/%0d",
                             eye_at(eye_edge0, eye_o0),
                             eye_at(eye_edge1, cliff_cen));
                    $fflush();
                end else if (have && best_w > best_row) begin
                    eye_cen0 <= eye_o0;
                    eye_cen1 <= best_lo + (best_w >> 1);
                    best_row <= best_w;
                    if (outer_end) begin
                        eye_lock0 <= eye_at(eye_edge0, eye_o0);
                        eye_lock1 <= eye_at(eye_edge1, best_lo + (best_w >> 1));
                        eye_lock <= 1'b1;
                        eye_mode <= 1'b0;
                        eye_commit <= 1'b1;
                        $display("EYE pass %0d/%0d",
                                 eye_at(eye_edge0, eye_o0),
                                 eye_at(eye_edge1, best_lo + (best_w >> 1)));
                        $fflush();
                    end else begin
                        eye_o0 <= eye_o0 + 8'd1;
                        eye_bo <= 8'd0;
                        in_run <= 1'b0;
                        have <= 1'b0;
                        best_w <= 8'd0;
                        cliff_run <= 1'b0;
                        have_cliff <= 1'b0;
                        eye_st <= E_SETTLE;
                    end
                end else if (outer_end && best_row != 8'd0) begin
                    eye_lock0 <= eye_at(eye_edge0, eye_cen0);
                    eye_lock1 <= eye_at(eye_edge1, eye_cen1);
                    eye_lock <= 1'b1;
                    eye_mode <= 1'b0;
                    eye_commit <= 1'b1;
                    $display("EYE pass %0d/%0d",
                             eye_at(eye_edge0, eye_cen0),
                             eye_at(eye_edge1, eye_cen1));
                    $fflush();
                end else if (outer_end) begin
                    eye_mode <= 1'b0;
                    $display("EYE fail");
                    $fflush();
                end else begin
                    eye_o0 <= eye_o0 + 8'd1;
                    eye_bo <= 8'd0;
                    in_run <= 1'b0;
                    have <= 1'b0;
                    best_w <= 8'd0;
                    cliff_run <= 1'b0;
                    have_cliff <= 1'b0;
                    eye_st <= E_SETTLE;
                end
            end
            default: eye_st <= E_SETTLE;
        endcase
    end
end

// Monitor rburst pulses and set rburst_seen when one is seen
always @(posedge pclk) begin
    if (rburst[0]) rburst_seen[0] <= 1'b1;
    if (rburst[1]) rburst_seen[1] <= 1'b1;
    if ({state,cycle} == {READ_CALIB, FIVEB'(RCD/4)})   // when we send read calibration req.
        rburst_seen <= 2'b0;
    if (~rst_lock_n) begin
        rburst_seen <= 2'b0;
    end
end

// Output READ pulse is for detecting DQS signal
// RCLKSEL shifts READ pulse by 1/4 CK per step
// Read calibration is done by first trying all RCLKSEL values (total 8)
// Then move READ pulse to next cycle (total 4). So there're 32 positions to try.
// When signals align, there will be a RBURST pulse.
always @(posedge pclk) begin
    dqs_read <= 0;
    if ((state == READ || state == READ_CALIB) 
            && cycle == FIVEB'(rclkpos+RCD/4+1)) begin
        dqs_read <= 4'b1111;
    end
end

//
// SERDES IOLOGIC for DDR3
//
wire [7:0] dllstep;

`ifdef SIM
// SIM shortcut. The DLL primitive takes 33600 cycles to lock.
assign dllstep = 8'd25;
assign dlllock = 1'b1;
`else
// SCAL_EN=="false" means constant output of 
// Every DLL step is about 0.025 ns. For 100Mhz, dllstep should be roughly 0.625/0.025=25
DLL #(
    .SCAL_EN("true"), .CODESCAL("101")     // 68-degree phase shift
//    .SCAL_EN("false")                     // 90° phase shift
) dll(
    .CLKIN(fclk), .RESET(~resetn), .STOP(0), 
    .UPDNCNTL(1'b0), .STEP(dllstep), .LOCK(dlllock)
);
`endif

wire [2:0] dqs_waddr[1:0], dqs_raddr[1:0];
wire clk_dqsr[1:0];
wire clk_dqsw[1:0];
wire clk_dqsw270[1:0];
// genvar is declared outside the for-loop. Icarus treats
// `for (genvar i = ...)` as a variable and then rejects the
// loop index on a primitive output port.
genvar i0, i1, i2, i3, i4;
generate
    // ck is fclk delayed 90 degrees with PLL
    // DQSR90 is DQSIN delayed DLLSTEP.
    // DQSW0 is fclk delayed WSTEP
    // DQSW270 is fclk delayed WSTEP+DLLSTEP+180-degrees.
    for (i0 = 0; i0 < 2; i0 = i0 + 1) begin : gen_dqs_controller
        DQS #(
            .DQS_MODE("X4"), .HWL("false")       // HWL is related to WL&RL
            // .DQS_MODE("X4"), .HWL("true")   
        ) u_dqs (
            .FCLK(fclk), .PCLK(pclk), .DQSIN(DDR3_DQS[i0]), .RESET(~rst_lock_n), .HOLD(dqs_hold), 
            .RLOADN(1'b0), .WLOADN(wload_n), .RMOVE(1'b0), .WMOVE(1'b0),
            .DLLSTEP(dllstep), .WSTEP(i0 == 0 ? wstep_run : wstep1_run), // per-lane delay
            .RCLKSEL(rclksel), .READ(dqs_read),
            .DQSR90(clk_dqsr[i0]), .WPOINT(dqs_waddr[i0]), .RPOINT(dqs_raddr[i0]), 
            .DQSW0(clk_dqsw[i0]), .DQSW270(clk_dqsw270[i0]), .RBURST(rburst[i0])
        );
    end
endgenerate

// 2*CK speed in/out for data(DQ), data strobe(DQS) and data mask(DM)
wire [15:0] dq_buf, dq_buf_oen;        // I/O buffer internal use
generate
    for (i1 = 0; i1 < 16; i1 = i1 + 1) begin : gen_dq
        OSER8_MEM #(.TCLK_SOURCE("DQSW270")) oser_dq(
            .D0(dq_out[0][i1]), .D1(dq_out[1][i1]), .D2(dq_out[2][i1]), .D3(dq_out[3][i1]), 
            .D4(dq_out[4][i1]), .D5(dq_out[5][i1]), .D6(dq_out[6][i1]), .D7(dq_out[7][i1]), 
            .TX0(dq_oen[0]), .TX1(dq_oen[1]), .TX2(dq_oen[2]), .TX3(dq_oen[3]), 
            .FCLK(fclk), .PCLK(pclk), .TCLK(clk_dqsw270[i1/8]), .RESET(~rst_lock_n|| ~dlllock), 
            .Q0(dq_buf[i1]), .Q1(dq_buf_oen[i1])
        );
        assign DDR3_DQ[i1] = dq_buf_oen[i1] ? 1'bz : dq_buf[i1];

        // The fifo is for clock domain crossing from DQS to fclk
        IDES8_MEM iser_dq(
            .D(DDR3_DQ[i1]), .ICLK(clk_dqsr[i1/8]), .FCLK(fclk), .PCLK(pclk), .CALIB(1'b0), .RESET(~rst_lock_n), 
            .Q0(dq_in[0][i1]), .Q1(dq_in[1][i1]), .Q2(dq_in[2][i1]), .Q3(dq_in[3][i1]), 
            .Q4(dq_in[4][i1]), .Q5(dq_in[5][i1]), .Q6(dq_in[6][i1]), .Q7(dq_in[7][i1]), 
            .WADDR(dqs_waddr[i1/8]), .RADDR(dqs_raddr[i1/8])
        );
    end
endgenerate

// DQS[1:0], DM[1:0]
wire [1:0] dqs_buf, dqs_buf_oen;
wire [1:0] dqs_buf_delayed;
generate
    for (i2 = 0; i2 < 2; i2 = i2 + 1) begin : gen_dqs
        // DQS is output using the DQSW0
        OSER8_MEM oser_dqs(
             .D0(dqs_out[0]), .D1(dqs_out[1]), .D2(dqs_out[2]), .D3(dqs_out[3]), 
             .D4(dqs_out[4]), .D5(dqs_out[5]), .D6(dqs_out[6]), .D7(dqs_out[7]), 
             .TX0(dqs_oen[0]), .TX1(dqs_oen[1]), .TX2(dqs_oen[2]), .TX3(dqs_oen[3]), 
             .FCLK(fclk), .PCLK(pclk), .TCLK(clk_dqsw[i2]), .RESET(~rst_lock_n), 
             .Q0(dqs_buf[i2]), .Q1(dqs_buf_oen[i2])
        );
        assign DDR3_DQS[i2] = dqs_buf_oen[i2] ? 1'bz : dqs_buf[i2];

        // DM is aligned with DQ
        OSER8_MEM #(.TCLK_SOURCE("DQSW270")) oser_dm(
            .D0(dm_out[0]), .D1(dm_out[1]), .D2(dm_out[2]), .D3(dm_out[3]), 
            .D4(dm_out[4]), .D5(dm_out[5]), .D6(dm_out[6]), .D7(dm_out[7]), 
            .FCLK(fclk), .PCLK(pclk), .TCLK(clk_dqsw270[i2]), .RESET(~rst_lock_n), .Q0(DDR3_DM[i2])
        );
    end
endgenerate

// CK speed output for nRAS, nCAS, nWE
OSER8 oser_nras(
    .D0(nRAS[0]), .D1(nRAS[0]), .D2(nRAS[1]), .D3(nRAS[1]), 
    .D4(nRAS[2]), .D5(nRAS[2]), .D6(nRAS[3]), .D7(nRAS[3]), 
    .FCLK(fclk), .PCLK(pclk), .RESET(~rst_lock_n), .Q0(DDR3_nRAS)
);
OSER8 oser_ncas(
    .D0(nCAS[0]), .D1(nCAS[0]), .D2(nCAS[1]), .D3(nCAS[1]), 
    .D4(nCAS[2]), .D5(nCAS[2]), .D6(nCAS[3]), .D7(nCAS[3]), 
    .FCLK(fclk), .PCLK(pclk), .RESET(~rst_lock_n), .Q0(DDR3_nCAS)
);
OSER8 oser_nwe(
    .D0(nWE[0]), .D1(nWE[0]), .D2(nWE[1]), .D3(nWE[1]), 
    .D4(nWE[2]), .D5(nWE[2]), .D6(nWE[3]), .D7(nWE[3]), 
    .FCLK(fclk), .PCLK(pclk), .RESET(~rst_lock_n), .Q0(DDR3_nWE)
);

// Address lines (CK speed)
generate
    for (i3 = 0; i3 < ROW_WIDTH; i3 = i3 + 1) begin: gen_a
        OSER8 oser_a(
            .D0(A[0][i3]), .D1(A[0][i3]), .D2(A[1][i3]), .D3(A[1][i3]), 
            .D4(A[2][i3]), .D5(A[2][i3]), .D6(A[3][i3]), .D7(A[3][i3]), 
            .FCLK(fclk), .PCLK(pclk), .RESET(~rst_lock_n), .Q0(DDR3_A[i3])
        );
    end
endgenerate

// BA lines (CK speed)
generate
    for (i4 = 0; i4 < 3; i4 = i4 + 1) begin: gen_ba
        OSER8 oser_ba(
            .D0(BA[0][i4]), .D1(BA[0][i4]), .D2(BA[1][i4]), .D3(BA[1][i4]), 
            .D4(BA[2][i4]), .D5(BA[2][i4]), .D6(BA[3][i4]), .D7(BA[3][i4]), 
            .FCLK(fclk), .PCLK(pclk), .RESET(~rst_lock_n), .Q0(DDR3_BA[i4])
        );
    end
endgenerate

endmodule