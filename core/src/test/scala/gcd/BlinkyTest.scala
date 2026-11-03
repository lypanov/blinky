package gcd

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class BlinkyTest extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "Blinky"

  it should "blink at 1 Hz, then 2 Hz when speedup is pressed, then back to 1 Hz" in {
    test(new Blinky(1, 1000)) { dut =>
      // Set timeout to allow enough cycles for all blinks
      // 2 blinks at 1 Hz = 2 * 500 = 1000 cycles
      // 5 blinks at 2 Hz = 5 * 250 = 1250 cycles
      // 1 blink at 1 Hz = 500 cycles
      // Total ~ 2750 cycles, add buffer -> 3000 cycles
      dut.clock.setTimeout(3000)

      // Helper function to wait for a specific number of blinks and verify frequency
      def waitForBlinksAndVerifyFrequency(n: Int, expectedFrequency: Double): Unit = {
        val expectedCyclesPerBlink = 1000.0 / expectedFrequency / 2 // divide by 2 for half-cycle (on->off or off->on)
        val allowedDeviation = 0.1 * expectedCyclesPerBlink // Allow 10% deviation

        var blinks = 0
        var prevLed = dut.io.led.peek().litToBoolean
        var cyclesSinceLastToggle = 0
        val cycleTimes = scala.collection.mutable.ArrayBuffer[Int]()

        while (blinks < n) {
          dut.clock.step()
          cyclesSinceLastToggle += 1
          
          val currentLed = dut.io.led.peek().litToBoolean
          if (prevLed != currentLed) { // LED toggled
            if (blinks > 0) { // Skip the first toggle to ensure we have a complete cycle
              cycleTimes += cyclesSinceLastToggle
            }
            cyclesSinceLastToggle = 0
            blinks += 1
          }
          prevLed = currentLed
        }

        // Verify the frequency by checking the cycle times
        println(s"Cycles between toggles: ${cycleTimes.mkString(", ")}")
        
        val avgCycles = cycleTimes.sum.toDouble / cycleTimes.size
        println(s"Average cycles per toggle: $avgCycles (expected: $expectedCyclesPerBlink)")
        
        avgCycles should be (expectedCyclesPerBlink +- allowedDeviation)
      }

      dut.io.speed_up_n.poke(true.B)
      println("Test started, initial speed: 1 Hz")

      waitForBlinksAndVerifyFrequency(4, 1.0) // Measure 4 toggles (2 full blinks) at 1 Hz
      println("2 blinks completed and verified at 1 Hz")

      dut.io.speed_up_n.poke(false.B)
      println("Speed-up button pressed, frequency should increase to 2 Hz")

      waitForBlinksAndVerifyFrequency(10, 2.0) // Measure 10 toggles (5 full blinks) at 2 Hz
      println("5 blinks completed and verified at 2 Hz")

      dut.io.speed_up_n.poke(true.B)
      println("Speed-up button released, frequency should return to 1 Hz")

      waitForBlinksAndVerifyFrequency(2, 1.0) // Measure 2 toggles (1 full blink) at 1 Hz
      println("1 blink completed and verified at 1 Hz, test ending")
    }
  }
}