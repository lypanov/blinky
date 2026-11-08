// clk_out/2. DIV_MODE 2 is an edge-aligned divide of HCLKIN.

module GowinClkDiv2 (
  input  HCLKIN,
  input  RESETN,
  input  CALIB,
  output CLKOUT
);
  CLKDIV u_div (
    .HCLKIN (HCLKIN),
    .RESETN (RESETN),
    .CALIB  (CALIB),
    .CLKOUT (CLKOUT)
  );
  defparam u_div.DIV_MODE = "2";
  defparam u_div.GSREN = "false";
endmodule
