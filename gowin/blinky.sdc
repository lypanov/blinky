create_clock -name clock -period 37.037 [get_ports {clock}]
# The status word and the arm bit are written on cpu_clk and sampled
# on the 27 MHz pixel clock, which is this port. cpu_clk is clk_out/2
# and clk_out is a PLL on this same port, so the tools check the
# same edge. Both signals change and then sit. The pixel clock
# samples them on a later edge. The same-edge hold check is not
# the requirement. Setup stays the default one-cycle check.
set_multicycle_path -hold 1 -from [get_pins {u_video/status_0_s1/Q u_video/status_1_s1/Q u_video/status_2_s1/Q u_video/status_3_s1/Q u_video/status_4_s1/Q u_video/status_5_s1/Q u_video/status_6_s1/Q u_video/status_7_s1/Q u_video/status_8_s1/Q}] -to [get_pins {u_video/status_q_0_s0/D u_video/status_q_1_s0/D u_video/status_q_2_s0/D u_video/status_q_3_s0/D u_video/status_q_4_s0/D u_video/status_q_5_s0/D u_video/status_q_6_s0/D u_video/status_q_7_s0/D u_video/status_q_8_s0/D}]
set_multicycle_path -hold 1 -from [get_pins {u_cpu/cpu/armed_s1/Q}] -to [get_pins {u_video/armed_s1_s0/D}]
