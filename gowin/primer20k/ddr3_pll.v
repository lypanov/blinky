// GW2A-18C rPLL for the Dock DDR3 PHY.
// 27 MHz * 43 / 3 = 387 MHz memory clock. CLKOUTD divides that by 4,
// which is the 96.75 MHz controller clock. CLKOUTP is that memory
// clock shifted 90 degrees, and it is DDR3_CK. These dividers are the
// ones that already initialized H5TQ1G63 on this Dock.

module ddr3_pll (
  input  clkin,
  input  reset,
  output clkout,
  output clkoutp,
  output clkoutd,
  output lock
);
  wire gnd;
  assign gnd = 1'b0;

  rPLL pll (
    .CLKOUT   (clkout),
    .LOCK     (lock),
    .CLKOUTP  (clkoutp),
    .CLKOUTD  (clkoutd),
    .CLKOUTD3 (),
    .RESET    (reset),
    .RESET_P  (gnd),
    .CLKIN    (clkin),
    .CLKFB    (gnd),
    .FBDSEL   ({gnd, gnd, gnd, gnd, gnd, gnd}),
    .IDSEL    ({gnd, gnd, gnd, gnd, gnd, gnd}),
    .ODSEL    ({gnd, gnd, gnd, gnd, gnd, gnd}),
    .PSDA     ({gnd, gnd, gnd, gnd}),
    .DUTYDA   ({gnd, gnd, gnd, gnd}),
    .FDLY     ({gnd, gnd, gnd, gnd})
  );

  defparam pll.FCLKIN = "27";
  defparam pll.IDIV_SEL = 2;
  defparam pll.FBDIV_SEL = 42;
  defparam pll.ODIV_SEL = 2;
  defparam pll.PSDA_SEL = "0100";
  defparam pll.DYN_SDIV_SEL = 4;
  defparam pll.CLKOUTD_SRC = "CLKOUT";
  defparam pll.CLKOUTD3_SRC = "CLKOUT";
  defparam pll.DYN_IDIV_SEL = "false";
  defparam pll.DYN_FBDIV_SEL = "false";
  defparam pll.DYN_ODIV_SEL = "false";
  defparam pll.DYN_DA_EN = "false";
  defparam pll.DUTYDA_SEL = "1000";
  defparam pll.CLKOUT_FT_DIR = 1'b1;
  defparam pll.CLKOUTP_FT_DIR = 1'b1;
  defparam pll.CLKOUT_DLY_STEP = 0;
  defparam pll.CLKOUTP_DLY_STEP = 0;
  defparam pll.CLKFB_SEL = "internal";
  defparam pll.CLKOUT_BYPASS = "false";
  defparam pll.CLKOUTP_BYPASS = "false";
  defparam pll.CLKOUTD_BYPASS = "false";
  defparam pll.DEVICE = "GW2A-18C";
endmodule
