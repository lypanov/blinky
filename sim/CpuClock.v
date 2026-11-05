// pclk/4, edge-aligned, 50% duty. The bridge samples a CPU output on a
// later posedge of clk_in. Matches Gowin CLKDIV DIV_MODE "4".

module CpuClock (
  input  clk_in,
  output reg clk_out
);
  reg [1:0] phase = 2'b00;
  initial begin
    clk_out = 1'b0;
    if (!$value$plusargs("cpu_phase=%d", phase))
      phase = 2'b00;
  end
  always @(posedge clk_in) begin
    if (phase == 2'b11)
      clk_out <= 1'b1;
    else if (phase == 2'b01)
      clk_out <= 1'b0;
    phase <= phase + 2'b01;
  end
endmodule
