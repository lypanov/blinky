create_clock -name Clock -period 37.037 [get_ports {Clock}]
create_clock -name pclk -period 10.336 [get_nets {pclk}]
create_generated_clock -name cpu_clk -source [get_nets {pclk}] -divide_by 4 [get_nets {cpu_clk}]
# The clocks are edge-aligned. A CPU output is sampled on the next pclk.
# A bridge output is launched on pclk and is allowed two pclk to reach the
# CPU: the CPU edge is four pclk after the request, and stall rises on the
# pclk after that request. Two pclk still arrives before that CPU edge.
# The same-edge hold check is not the requirement.
set_multicycle_path -hold 1 -from [get_clocks {cpu_clk}] -to [get_clocks {pclk}]
set_multicycle_path -hold 1 -from [get_clocks {pclk}] -to [get_clocks {cpu_clk}]
set_max_delay -from [get_clocks {pclk}] -to [get_clocks {cpu_clk}] 20.672
