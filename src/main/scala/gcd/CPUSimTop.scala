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
 * (maxIterations = 262144, 2x delay) via CPUSubset0.main / build.sh.
 */
class CPUSimTop(
    programInstructions: Seq[String],
    customMemoryImage: Option[Seq[String]] = None,
    memBackend: String = "blockram",
    hyperFirstValid: Int = 12,
    extraChecks: Int = 0,
    fetchStored: Boolean = false,
    chainFix: Boolean = false
) extends Module {
  val hyper = memBackend == "hyperram"
  val ddr3 = memBackend == "ddr3"
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

  val cpuClock = if (ddr3) {
    val half = Module(new CpuClock)
    half.io.clk_in := clock
    half.io.clk_out
  } else clock
  val cpu = withClock(cpuClock) { Module(new CPUSubset0(
    programInstructions,
    customMemoryImage = customMemoryImage,
    waitForStores = hyper || ddr3,
    requireMemCheck = hyper || ddr3,
    extraChecks = extraChecks,
    fetchStored = fetchStored,
    chainFix = chainFix
  )) }
  if (hyper) {
    val bridge = Module(new HyperRamBridge)
    val model = Module(new HyperRamUserModel(hyperFirstValid))
    bridge.io.cpuAddr := cpu.io.memAddr
    bridge.io.cpuWriteData := cpu.io.memWriteData
    bridge.io.cpuWrite := cpu.io.memWrite
    bridge.io.cpuRead := cpu.io.memRead
    bridge.io.cpuByte := cpu.io.memByte
    cpu.io.memReadData := bridge.io.cpuReadData
    cpu.io.memStall := bridge.io.memStall
    model.io.clk := clock
    model.io.memory_clk := clock
    model.io.pll_lock := true.B
    model.io.rst_n := ~reset.asBool
    model.io.cmd := bridge.io.hr.cmd
    model.io.cmd_en := bridge.io.hr.cmd_en
    model.io.addr := bridge.io.hr.addr
    model.io.wr_data := bridge.io.hr.wr_data
    model.io.data_mask := bridge.io.hr.data_mask
    bridge.io.hr.rd_data := model.io.rd_data
    bridge.io.hr.rd_data_valid := model.io.rd_data_valid
    bridge.io.hr.init_calib := model.io.init_calib
  } else if (ddr3) {
    val bridge = Module(new Ddr3Bridge)
    val model = Module(new Ddr3UserModel)
    val sync = withClock(cpuClock) { Module(new Ddr3CpuPortSync) }
    sync.io.inAddr := cpu.io.memAddr
    sync.io.inWriteData := cpu.io.memWriteData
    sync.io.inWrite := cpu.io.memWrite
    sync.io.inRead := cpu.io.memRead
    sync.io.inByte := cpu.io.memByte
    bridge.io.cpuAddr := sync.io.addr
    bridge.io.cpuWriteData := sync.io.writeData
    bridge.io.cpuWrite := sync.io.write
    bridge.io.cpuRead := sync.io.read
    bridge.io.cpuByte := sync.io.byte
    cpu.io.memReadData := bridge.io.cpuReadData
    val align = withClock(cpuClock) { Module(new Ddr3StallAlign) }
    align.io.req := cpu.io.memRead || cpu.io.memWrite
    align.io.bridgeStall := bridge.io.memStall
    cpu.io.memStall := align.io.stall
    model.io.clk := clock
    model.io.rst_n := ~reset.asBool
    model.io.rd := bridge.io.ddr.rd
    model.io.wr := bridge.io.ddr.wr
    model.io.refresh := bridge.io.ddr.refresh
    model.io.addr := bridge.io.ddr.addr
    model.io.din := bridge.io.ddr.din
    bridge.io.ddr.dout := model.io.dout
    bridge.io.ddr.data_ready := model.io.data_ready
    bridge.io.ddr.busy := model.io.busy
    bridge.io.ddr.calib := model.io.calib
  } else {
    val memoryController = Module(new MemoryController(useRealGowin = false))
    memoryController.io.cpuAddr := cpu.io.memAddr
    memoryController.io.cpuWriteData := cpu.io.memWriteData
    memoryController.io.cpuWrite := cpu.io.memWrite
    memoryController.io.cpuRead := cpu.io.memRead
    cpu.io.memReadData := memoryController.io.cpuReadData
    cpu.io.memStall := false.B
  }

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
    val image = sys.env.getOrElse("SIM_IMAGE", "blink2")
    val targetDir = "generated"
    new File(targetDir).mkdirs()

    val (gen, outFile, label) = image match {
      case "blink3" =>
        val imemPath = new File(
          projectRoot,
          sys.env.getOrElse("BLINK3_IMEM", "sim/visualizer/imem/blink3.words")
        ).getAbsolutePath
        val words = loadInstructionsFromFile(imemPath)
        println(s"CPUSimTop: Blink3 custom IMEM ${words.length} words from $imemPath")
        (
          () => new CPUSimTop(Seq.empty, customMemoryImage = Some(words)),
          s"$targetDir/CPUSimTopBlink3.v",
          "blink3"
        )
      case "ddr3" | "ddr3fixup" | "ddr3rsc" =>
        val extra = if (image == "ddr3rsc") 32 else if (image == "ddr3fixup") 20 else 0
        val imemPath = new File(
          projectRoot,
          sys.env.getOrElse(
            "BLINK3_IMEM",
            if (image == "ddr3rsc") "sim/visualizer/imem/ddr3rsc.words"
            else if (image == "ddr3fixup") "sim/visualizer/imem/ddr3fixup.words"
            else "sim/visualizer/imem/ddr3.words"
          )
        ).getAbsolutePath
        val words = loadInstructionsFromFile(imemPath)
        println(s"CPUSimTop: $image IMEM ${words.length} words extraChecks=$extra from $imemPath")
        (
          () => new CPUSimTop(
            Seq.empty,
            customMemoryImage = Some(words),
            memBackend = "ddr3",
            extraChecks = extra
          ),
          s"$targetDir/CPUSimTopDdr3.v",
          image
        )
      case "hyperram" | "fixup" | "rsc" | "fetchbl" | "pdchain" | "moddesc" | "files" | "modules" =>
        val imemPath = new File(
          projectRoot,
          sys.env.getOrElse(
            "BLINK3_IMEM",
            if (image == "modules") "sim/visualizer/imem/modules.words"
            else if (image == "files") "sim/visualizer/imem/files.words"
            else if (image == "moddesc") "sim/visualizer/imem/moddesc.words"
            else if (image == "pdchain") "sim/visualizer/imem/pdchain.words"
            else if (image == "fetchbl") "sim/visualizer/imem/fetchbl.words"
            else if (image == "rsc") "sim/visualizer/imem/rsc.words"
            else if (image == "fixup") "sim/visualizer/imem/fixup.words"
            else "sim/visualizer/imem/hyperram.words"
          )
        ).getAbsolutePath
        val words = loadInstructionsFromFile(imemPath)
        // 12 is the pre-load model. Later HyperRAM images simulate the fitted
        // read latency unless HYPER_FIRST_VALID overrides it.
        val firstValid = sys.env.get("HYPER_FIRST_VALID").map(_.toInt).getOrElse(
          if (image == "hyperram") 12 else 13
        )
        val extra = image match {
          case "modules" => 40
          case "files" => 40
          case "moddesc" => 40
          case "pdchain" => 37
          case "fetchbl" => 34
          case "rsc" => 32
          case "fixup" => 20
          case _ => 0
        }
        // FETCH_STORED=0 is the split-bus sim: same words, ROM fetch. Dark.
        val fetchStored = image == "fetchbl" && sys.env.getOrElse("FETCH_STORED", "1") != "0"
        // CHAIN_FIX=0 is the same words with no patch table and no ROM read
        // of the code window. The walk loads zeros and the pin stays dark.
        val chainFix = (image == "pdchain" || image == "moddesc" || image == "files" || image == "modules") && sys.env.getOrElse("CHAIN_FIX", "1") != "0"
        println(s"CPUSimTop: $image IMEM ${words.length} words from $imemPath")
        println(s"CPUSimTop: FIRST_VALID=$firstValid extraChecks=$extra fetchStored=$fetchStored chainFix=$chainFix")
        (
          () => new CPUSimTop(
            Seq.empty,
            customMemoryImage = Some(words),
            memBackend = "hyperram",
            hyperFirstValid = firstValid,
            extraChecks = extra,
            fetchStored = fetchStored,
            chainFix = chainFix
          ),
          s"$targetDir/CPUSimTopHyper.v",
          image
        )
      case _ =>
        val defaultCode = new File(projectRoot, "tests/Blink2test.code").getAbsolutePath
        val codePath = sys.env.getOrElse("BLINK2_CODE", defaultCode)
        val programInstructions = loadInstructionsFromFile(codePath)
        println(s"CPUSimTop: loaded ${programInstructions.length} instructions from $codePath")
        (
          () => new CPUSimTop(programInstructions),
          s"$targetDir/CPUSimTop.v",
          "blink2"
        )
    }

    val verilog = ChiselStage.emitSystemVerilog(
      gen = gen(),
      firtoolOpts = Array(
        "-disable-all-randomization",
        "-strip-debug-info",
        "--lowering-options=disallowLocalVariables,disallowPackedArrays,noAlwaysComb"
      )
    )

    val writer = new java.io.PrintWriter(new File(outFile))
    writer.write(verilog)
    writer.close()
    println(s"Simulation Verilog ($label) written to $outFile")
  }
}
