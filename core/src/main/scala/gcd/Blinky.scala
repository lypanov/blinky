package gcd

import chisel3._
import _root_.circt.stage.ChiselStage

class Blinky(frequency: Int, clockFreq: Int) extends Module {
  val io = IO(new Bundle {
    val led = Output(Bool())
    val speed_up_n = Input(Bool()) // active-low (0 when pressed)
  })

  val baseFreq = frequency.U
  val speedUpFactor = 2.U // Speed up by 2x when speed_up button is pressed
  
  val currentFreq = Mux(io.speed_up_n, baseFreq, baseFreq * speedUpFactor)
  val toggleFreq = clockFreq.U / (2.U * currentFreq)
  
  val counter = RegInit(0.U(32.W))
  val ledState = RegInit(false.B)

  counter := counter + 1.U
  when (counter >= toggleFreq) {
    counter := 0.U
    ledState := ~ledState
    printf(cf"LED toggled to ${ledState} at frequency ${currentFreq} Hz\n")
  }

  when (counter === 0.U) {
    printf(cf"Counter reset, current blink frequency: ${currentFreq} Hz\n")
  }

  io.led := ledState
}

object Blinky {
  def main(args: Array[String]): Unit = {
    println("Generating Blinky Verilog")
    
    val targetDir = "generated"
    val outputFile = "Blinky.v"
    
    new java.io.File(targetDir).mkdirs()
    
    val verilogCode = ChiselStage.emitSystemVerilog(
      gen = new Blinky(1, 27_000_000), // 1 Hz blink, 27 MHz Tang Nano 4K clock
      firtoolOpts = Array("-disable-all-randomization", "-strip-debug-info",
         "--lowering-options=disallowLocalVariables")
    )
    
    val writer = new java.io.PrintWriter(new java.io.File(s"$targetDir/$outputFile"))
    writer.write(verilogCode)
    writer.close()
    
    println(s"Verilog written to $targetDir/$outputFile")
  }
}