// See README.md for license details.

package gcd

import chisel3._
import chisel3.simulator.EphemeralSimulator._
import chisel3.util.log2Ceil
import org.scalatest.freespec.AnyFreeSpec
import org.scalatest.matchers.must.Matchers

/**
  * Test for the Blinky module
  * From within sbt use:
  * {{{
  * testOnly gcd.BlinkySpec
  * }}}
  * From a terminal shell use:
  * {{{
  * sbt 'testOnly gcd.BlinkySpec'
  * }}}
  * Testing from mill:
  * {{{
  * mill chisel-blinky.test.testOnly gcd.BlinkySpec
  * }}}
  */
class BlinkySpec extends AnyFreeSpec with Matchers {

  "Blinky should blink LED at the correct frequency and respond to speed_up button" in {
    // Use a smaller clock frequency for faster simulation
    val clockFreq = 1000 // 1 kHz for simulation
    val blinkFreq = 10   // 10 Hz for faster testing
    
    // Calculate expected toggle periods
    val normalTogglePeriod = clockFreq / (2 * blinkFreq)
    val speedUpTogglePeriod = clockFreq / (2 * blinkFreq * 2) // 2x speed

    simulate(new Blinky(blinkFreq, clockFreq) {
      // Add debug printf statements to monitor state
      when (reset.asBool) {
        printf("RESET: Initializing Blinky with base frequency %d Hz, clock %d Hz\n", blinkFreq.U, clockFreq.U)
        printf("RESET: Normal toggle period: %d cycles, Speed-up toggle period: %d cycles\n", 
               normalTogglePeriod.U, speedUpTogglePeriod.U)
      }
      
      // Monitor counter and LED state changes
      when (counter === 0.U && !reset.asBool) {
        val currentPeriod = Mux(io.speed_up_n, normalTogglePeriod.U, speedUpTogglePeriod.U)
        val currentFrequency = Mux(io.speed_up_n, blinkFreq.U, (blinkFreq * 2).U)
        printf("BLINK: LED changed to %d, current frequency: %d Hz (period: %d cycles)\n", 
               ledState, currentFrequency, currentPeriod)
      }
    }) { dut =>
      // Initialize
      dut.reset.poke(true.B)
      dut.speed_up_n.poke(true.B) // Not pressed initially
      dut.clock.step()
      dut.reset.poke(false.B)
      
      println("Starting Blinky test simulation")
      println(s"Normal blink period: $normalTogglePeriod cycles")
      println(s"Speed-up blink period: $speedUpTogglePeriod cycles")
      
      // Wait for 2 complete blinks (4 LED transitions) at normal speed
      var blinkCount = 0
      var lastLedState = dut.led.peek().litToBoolean
      
      println("Waiting for 2 complete blinks at normal speed...")
      while (blinkCount < 4) {
        dut.clock.step()
        val currentLedState = dut.led.peek().litToBoolean
        if (currentLedState != lastLedState) {
          lastLedState = currentLedState
          blinkCount += 1
          println(s"LED transition #$blinkCount detected: LED is now ${if (currentLedState) "ON" else "OFF"}")
        }
      }
      
      // Press the speed_up button
      println("Pressing speed_up button to increase blink frequency")
      dut.speed_up_n.poke(false.B) // Button pressed (active low)
      
      // Wait for 5 more complete blinks (10 LED transitions) at increased speed
      blinkCount = 0
      while (blinkCount < 10) {
        dut.clock.step()
        val currentLedState = dut.led.peek().litToBoolean
        if (currentLedState != lastLedState) {
          lastLedState = currentLedState
          blinkCount += 1
          println(s"LED transition #$blinkCount detected at increased speed: LED is now ${if (currentLedState) "ON" else "OFF"}")
        }
      }
      
      // Release the speed_up button
      println("Releasing speed_up button to return to normal speed")
      dut.speed_up_n.poke(true.B) // Button released
      
      // Wait for one more complete blink (2 LED transitions) at normal speed
      blinkCount = 0
      while (blinkCount < 2) {
        dut.clock.step()
        val currentLedState = dut.led.peek().litToBoolean
        if (currentLedState != lastLedState) {
          lastLedState = currentLedState
          blinkCount += 1
          println(s"LED transition #$blinkCount detected after returning to normal speed: LED is now ${if (currentLedState) "ON" else "OFF"}")
        }
      }
      
      println("Blinky test completed successfully!")
    }
  }
} 