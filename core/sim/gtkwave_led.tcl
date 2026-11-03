# GTKWave startup: add LED-related signals and zoom to the full run.
set sigs {
  CPUSimTop.clock
  CPUSimTop.reset
  CPUSimTop.io_led
  CPUSimTop.io_pc[31:0]
  CPUSimTop.io_r0[31:0]
  CPUSimTop.io_memWrite
  CPUSimTop.io_memAddr[31:0]
}
gtkwave::addSignalsFromList $sigs
set start [gtkwave::getMinTime]
set end [gtkwave::getMaxTime]
if {$end > $start} {
  gtkwave::setZoomRangeTimes $start $end
}
puts "GTKWave range $start .. $end"
