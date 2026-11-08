// clk_in/2, edge-aligned, 50% duty. Matches Gowin CLKDIV DIV_MODE "2".
// The HyperRAM bridge samples a CPU output on a later posedge of clk_in.

module CpuClock2 (
  input  clk_in,
  output reg clk_out
);
  initial clk_out = 1'b0;
  always @(posedge clk_in) begin
    clk_out <= ~clk_out;
  end
endmodule
