package gcd

import chisel3._
import _root_.circt.stage.ChiselStage
import java.io.File

/**
 * Simulation-only top: CPUSubset0 + mock RAM, no UART / Gowin IP.
 *
 * Does not change CPU behaviour. The Blink2 *program* loaded here is the
 * short-delay test image (maxIterations = 5) so a LED period is observable
 * in a few hundred cycles. Hardware still uses tests/Blink2hw.code
 * (maxIterations = 524288) via CPUSubset0.main / build.sh.
 */
class CPUSimTop(programInstructions: Seq[String]) extends Module {
  val io = IO(new Bundle {
    val led = Output(Bool())
    val pc = Output(UInt(32.W))
    val halted = Output(Bool())
    val r0 = Output(UInt(32.W))
    val r1 = Output(UInt(32.W))
    val r2 = Output(UInt(32.W))
    val r3 = Output(UInt(32.W))
    val memAddr = Output(UInt(32.W))
    val memWriteData = Output(UInt(32.W))
    val memWrite = Output(Bool())
    val memRead = Output(Bool())
  })

  val cpu = Module(new CPUSubset0(programInstructions))
  val memoryController = Module(new MemoryController(useRealGowin = false))

  memoryController.io.cpuAddr := cpu.io.memAddr
  memoryController.io.cpuWriteData := cpu.io.memWriteData
  memoryController.io.cpuWrite := cpu.io.memWrite
  memoryController.io.cpuRead := cpu.io.memRead
  cpu.io.memReadData := memoryController.io.cpuReadData

  io.led := cpu.io.led
  io.pc := cpu.io.pc
  io.halted := cpu.io.halted
  io.r0 := cpu.io.r0
  io.r1 := cpu.io.r1
  io.r2 := cpu.io.r2
  io.r3 := cpu.io.r3
  io.memAddr := cpu.io.memAddr
  io.memWriteData := cpu.io.memWriteData
  io.memWrite := cpu.io.memWrite
  io.memRead := cpu.io.memRead
}

object CPUSimTop {
  private def getProjectRoot(): String = {
    Option(System.getenv("CHISEL_CPU_PROJECT_ROOT")).getOrElse {
      var current = new File(sys.props("user.dir"))
      while (current != null && !new File(current, "build.sc").exists() && !new File(current, "build.mill").exists()) {
        current = current.getParentFile
      }
      if (current != null) current.getAbsolutePath
      else sys.props("user.dir")
    }
  }

  def loadInstructionsFromFile(filePath: String): Seq[String] = {
    val source = scala.io.Source.fromFile(filePath)
    try {
      source.getLines()
        .map(_.trim)
        .filter(_.nonEmpty)
        .map(line => line.stripPrefix("0x"))
        .toSeq
    } finally {
      source.close()
    }
  }

  def main(args: Array[String]): Unit = {
    val projectRoot = getProjectRoot()
    val defaultCode = new File(projectRoot, "tests/Blink2test.code").getAbsolutePath
    val codePath = sys.env.getOrElse("BLINK2_CODE", defaultCode)
    val programInstructions = loadInstructionsFromFile(codePath)
    println(s"CPUSimTop: loaded ${programInstructions.length} instructions from $codePath")

    val targetDir = "generated"
    new File(targetDir).mkdirs()

    val verilog = ChiselStage.emitSystemVerilog(
      gen = new CPUSimTop(programInstructions),
      firtoolOpts = Array(
        "-disable-all-randomization",
        "-strip-debug-info",
        "--lowering-options=disallowLocalVariables,disallowPackedArrays,noAlwaysComb"
      )
    )

    val outFile = s"$targetDir/CPUSimTop.v"
    val writer = new java.io.PrintWriter(new File(outFile))
    writer.write(verilog)
    writer.close()
    println(s"Simulation Verilog written to $outFile")
  }
}
