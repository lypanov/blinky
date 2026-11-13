package gcd

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.io.{File, PrintWriter}
import gcd.Logger

// Clocked instruction ROM. A combinational case statement is LUT logic, and
// the fixup image does not fit the Nano 4K that way. Gowin maps this array
// plus the posedge read onto BSRAM, which has its own budget. The Verilog is
// written next to the hex file; it is not emitted into the Chisel output,
// because firtool's inline-blackbox trailer is not valid Verilog.
class InstrRom(depth: Int, addrBits: Int, hexPath: String) extends BlackBox {
  override def desiredName = "InstrRom"
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val addr = Input(UInt(addrBits.W))
    val data = Output(UInt(32.W))
    // One-cycle load of the output register from a word that was read back
    // out of HyperRAM. The decoder still sees this register. While overlayEn
    // is low the read is the same posedge ROM read as before.
    val overlayEn = Input(Bool())
    val overlayData = Input(UInt(32.W))
  })
  private val romFile = new File("generated/InstrRom.v")
  romFile.getParentFile.mkdirs()
  val romWriter = new PrintWriter(romFile)
  romWriter.write(
    s"""module InstrRom(
       |  input clk,
       |  input [${addrBits - 1}:0] addr,
       |  output reg [31:0] data,
       |  input overlayEn,
       |  input [31:0] overlayData
       |);
       |  ${if (depth <= 512) "(* syn_ramstyle = \"block_ram\" *) " else ""}reg [31:0] mem [0:${depth - 1}];
       |  initial $$readmemh("${hexPath}", mem);
       |  always @(posedge clk) begin
       |    if (overlayEn)
       |      data <= overlayData;
       |    else
       |      data <= mem[addr];
       |  end
       |endmodule
       |""".stripMargin)
  romWriter.close()
}


// Treadle does not run the Verilog black box, so the unit tests use this
// register. The address is the next PC and the word at the current PC is
// what comes out, which is the same read as InstrRom.
class ChiselInstrRom(words: Seq[String], addrBits: Int) extends Module {
  val io = IO(new Bundle {
    val addr = Input(UInt(addrBits.W))
    val data = Output(UInt(32.W))
    val overlayEn = Input(Bool())
    val overlayData = Input(UInt(32.W))
  })
  val mem = VecInit(words.map { token =>
    (java.lang.Long.parseLong(token, 16) & 0xffffffffL).U(32.W)
  })
  val data = Reg(UInt(32.W))
  when (io.overlayEn) {
    data := io.overlayData
  } .otherwise {
    data := mem(io.addr)
  }
  io.data := data
}

// RISC5 MUL. One plain 33×33 signed multiply, registered, so Gowin can
// map `*` onto the multiplier blocks and use the block's output register.
// A 33-bit operand is the 32-bit value with a zero or a copy of bit 31
// above it. The low 64 bits are the 32×32 product. Written out by hand:
// firtool sign-extends a Chisel SInt multiply to 66×66, and that is not
// the multiplier the FPGA has. The CPU presents the operands on the issue
// cycle and reads the product on the next cycle.
class HwMul extends BlackBox {
  override def desiredName = "HwMul"
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val x = Input(UInt(33.W))
    val y = Input(UInt(33.W))
    val p = Output(UInt(64.W))
  })
  private val mulFile = new File("generated/HwMul.v")
  mulFile.getParentFile.mkdirs()
  val mulWriter = new PrintWriter(mulFile)
  mulWriter.write(
    """module HwMul(
      |  input clk,
      |  input [32:0] x,
      |  input [32:0] y,
      |  output [63:0] p
      |);
      |  reg [65:0] bits;
      |  wire signed [32:0] xs = x;
      |  wire signed [32:0] ys = y;
      |  always @(posedge clk)
      |    bits <= xs * ys;
      |  assign p = bits[63:0];
      |endmodule
      |""".stripMargin)
  mulWriter.close()
}

// Sixteen register words, saved and restored one per cycle. The Nano 4K
// has no logic left for a second register file. gowin/FpSnap.v is one SP
// block; this file is the same port with a one-cycle read, for Verilator.
// A write leaves the output register alone, matching SP write mode 00.
class FpSnap extends BlackBox {
  override def desiredName = "FpSnap"
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val addr = Input(UInt(4.W))
    val we = Input(Bool())
    val wdata = Input(UInt(32.W))
    val rdata = Output(UInt(32.W))
  })
  private val snapFile = new File("generated/FpSnap.v")
  snapFile.getParentFile.mkdirs()
  val snapWriter = new PrintWriter(snapFile)
  snapWriter.write(
    """module FpSnap(
      |  input clk,
      |  input [3:0] addr,
      |  input we,
      |  input [31:0] wdata,
      |  output reg [31:0] rdata
      |);
      |  reg [31:0] mem [0:15];
      |  integer i;
      |  initial begin
      |    for (i = 0; i < 16; i = i + 1)
      |      mem[i] = 32'h0;
      |    rdata = 32'h0;
      |  end
      |  always @(posedge clk) begin
      |    if (we)
      |      mem[addr] <= wdata;
      |    else
      |      rdata <= mem[addr];
      |  end
      |endmodule
      |""".stripMargin)
  snapWriter.close()
}

// Same timing as FpSnap, for the treadle unit tests. The FPGA image
// uses the SP block instead.
class ChiselFpSnap extends Module {
  val io = IO(new Bundle {
    val addr = Input(UInt(4.W))
    val we = Input(Bool())
    val wdata = Input(UInt(32.W))
    val rdata = Output(UInt(32.W))
  })
  val mem = Reg(Vec(16, UInt(32.W)))
  when (io.we) {
    mem(io.addr) := io.wdata
  }
  val held = Reg(UInt(32.W))
  when (!io.we) {
    held := mem(io.addr)
  }
  io.rdata := held
}

class CPUSubset0(instructionHexStrings: Seq[String] = Seq.empty[String],
                 customMemoryImage: Option[Seq[String]] = None,
                 waitForStores: Boolean = false,
                 // The placed body, the copied core, and the trap are fetched
                 // from external memory. The ROM is only the bootstrap.
                 bodyFetch: Boolean = false,
                 chiselRom: Boolean = false,
                 core: Option[CoreMap] = None,
                 // Nano 4K disk boot. The ROM is only the bootstrap. The core
                 // is copied into HyperRAM and every later fetch comes from
                 // there.
                 flashBoot: Boolean = false,
                 // Dock disk boot. The same file arrives on the UART and is
                 // stored in DDR3. Training stays in this ROM.
                 uartDisk: Boolean = false) extends Module {
  val io = IO(new Bundle {
    val r0 = Output(UInt(32.W))  // Output register R0 for testing
    val r1 = Output(UInt(32.W))  // Output register R1 for testing
    val r2 = Output(UInt(32.W))  // Output register R2 for testing
    val r3 = Output(UInt(32.W))  // Output register R3 for testing
    // Prologue accumulators. At the 0x1390 hold, r0 is the OR of every
    // compare difference, r4/r5 are the pattern XOR and sum, r8/r9 the
    // complement XOR and sum, and r7 is the last load.
    val r4 = Output(UInt(32.W))
    val r5 = Output(UInt(32.W))
    val r7 = Output(UInt(32.W))
    val r8 = Output(UInt(32.W))
    val r9 = Output(UInt(32.W))
    val dbgMask = Output(UInt(40.W))
    val halted = Output(Bool())  // Signal to indicate when the CPU has completed execution
    val led = Output(Bool())     // LED output for the Tang Nano 4K
    val pc = Output(UInt(32.W))  // Program counter value for testing
    
    // Memory interface - allows the CPU to access external memory.
    // memStall holds the completion of a load (and, if waitForStores, a store).
    // Tied 0 with waitForStores=false, this is the block-RAM timing.
    val memAddr = Output(UInt(32.W))
    val memWriteData = Output(UInt(32.W))
    val memReadData = Input(UInt(32.W))
    val memWrite = Output(Bool())
    val memRead = Output(Bool())
    val memStall = Input(Bool())
    // v=1. The HyperRAM bridge writes one lane; a word access leaves this low
    // so the whole beat is written, which is the step-1 and step-2 path.
    val memByte = Output(Bool())

    // Logger boilerplate
    val messageCode = Output(UInt(4.W))
    val trigger = Output(Bool())
    val logByte = Output(UInt(8.W))

    // External NOR. Idle (CS high) unless this image is the flash bootstrap.
    val spiCsN = Output(Bool())
    val spiClk = Output(Bool())
    val spiMosi = Output(Bool())
    val spiMiso = Input(Bool())

    // The bitmap is ordinary words in two windows, both dropped here.
    // Bit 15 of the address picks the board: 0 is the 4K at 0xFFFE0000,
    // 1 is the Dock at 0xFFFE8000. This image writes one of them, and a
    // load reads the shadow of that write. The screen, when the build
    // has one, takes the pulse. -80 stays decoded and dropped; the
    // bitmap replaced that one block.
    val screenWe = Output(Bool())
    val screenBit = Output(Bool())
    val bmpData = Output(UInt(32.W))
    val bmpWord = Output(UInt(13.W))
    // Dock bitmap read. The shadow is on the pixel clock. This load
    // holds the request until the ack rises, then waits for it to fall.
    // The 4K image keeps its own shadow and does not use the ack.
    val bmpRdAddr = Output(UInt(13.W))
    val bmpRdReq = Output(Bool())
    val bmpRdData = Input(UInt(32.W))
    val bmpRdAck = Input(Bool())
    val armed = Output(Bool())
    // -84 (0xFFFFFFAC). Nine bits: the status byte, and bit 8 for the
    // screen mode. The store is dropped. The video module keeps the
    // register. A load is not decoded.
    val statusWe = Output(Bool())
    val statusWord = Output(UInt(9.W))

    // UART word port for the Dock disk. valid/word/take are the byte
    // assembler outside this module. A -72 load stalls until valid.
    val diskValid = Input(Bool())
    val diskWord = Input(UInt(32.W))
    val diskTake = Output(Bool())

    // -60, bit 0 of the book's switch word. 1 while the button is held
    // or the UART press latch is set. The sampler is outside, on this
    // same cpu clock. A board with neither ties it low.
    val btnPressed = Input(Bool())
    // -40 reads ones on the dark image. The good image ties this low,
    // and the word is 0: no key ready, mouse at the origin.
    val kbdOnes = Input(Bool())
  })
  
  // Initialize the logByte signal with a default value
  io.logByte := 0.U
  io.diskTake := false.B
  
  // Initialize PC: if a custom memory image is provided then start at 0x00 (for trampoline execution),
  // otherwise default to 0x80.
  val pc = RegInit(0x80.U(32.W))
  
  // Registers. One read port, below. All 16 stay.
  val regs = RegInit(VecInit(Seq.fill(16)(0.U(32.W))))
  
  // Flags
  val n = RegInit(false.B)  // Negative
  val c = RegInit(false.B)  // Carry
  val v = RegInit(false.B)  // Overflow
  val z = RegInit(false.B)  // Zero
  
  val memoryAccessPending = RegInit(false.B)
  val memoryTargetReg = RegInit(0.U(4.W))
  val memoryIsLoad = RegInit(false.B)
  val memoryIsByte = RegInit(false.B)
  val memoryLane = Reg(UInt(2.W))
  // The compiled image arms the LED from one store. The linker's
  // constant is the only value that sets the flip-flop. A skipped
  // check never looks like a pass.
  val splitFetch = core.isDefined
  val useArm = splitFetch
  val diskBoot = flashBoot || uartDisk
  if (uartDisk && flashBoot) {
    throw new RuntimeException("the UART disk and the NOR disk are different images")
  }
  if (diskBoot && (!splitFetch || !bodyFetch || chiselRom)) {
    throw new RuntimeException("disk boot needs the core map, the body fetch, and the BSRAM ROM")
  }
  if (splitFetch && !diskBoot) {
    throw new RuntimeException("the core map is the disk boot; the in-ROM translation is retired")
  }
  if (bodyFetch && !diskBoot) {
    throw new RuntimeException("body fetch is the disk boot")
  }
  io.spiCsN := true.B
  io.spiClk := false.B
  io.spiMosi := false.B
  val armAddrC = if (useArm) core.get.armAddr else 0
  val armWordC = if (useArm) core.get.armWord else 0L
  val armed = if (useArm) RegInit(false.B) else false.B
  
  // Instruction words. A combinational case-ROM of the fixup image did not
  // fit the GW1NSR-4C. This is a synchronous read so synthesis can use BSRAM
  // (the LUT budget does not count those blocks). The address presented this
  // cycle is the next PC, and reset presents 0x80, so the registered output
  // is the instruction at the current PC. That keeps the old one-instruction-
  // per-cycle timing, including the load stall.
  val imemWords: Seq[String] = {
    val raw = customMemoryImage match {
      case Some(mem) => mem
      case None =>
        val userProgEndAddr = 0x80 / 4
        val setupStartAddr = 0x80 / 4
        val setupEndAddr = 0xB0 / 4
        val haltStartAddr = 0xB0 / 4
        val haltEndAddr = 0xC0 / 4
        if (instructionHexStrings.length > userProgEndAddr) {
          throw new RuntimeException(s"Provided hex strings (${instructionHexStrings.length}) exceed the maximum allowed length ($userProgEndAddr)")
        }
        val userBeefCount = userProgEndAddr - instructionHexStrings.length
        val userBeefFiller = Seq.fill(userBeefCount)("0000BEEF")
        val setupInstructions = Seq(
          "4c000010", // MOV R12, 0x0010     ; MT (module top?)
          "4d000050", // MOV R13, 0x0050     ; setup variable block 0x50
          "adc00004", // STW R13, [R12, 0x04]
          "4dd80020", // ADD R13, [R13, 0x20]; now variable block 0x70
          "adc00008", // STW R13, [R12, 0x08]
          "4e000080", // MOV R14, 0x0080     ; Top of stack
          "4f0000B0", // MOV R15, 0x00B0     ; Halt address
          "40000000", // MOV R0, 0x0000      ; Clear R0 (function body)
          "c7000000"  // BT R0               ; Default branch (to user code)
        )
        val setupSize = setupEndAddr - setupStartAddr
        if (setupInstructions.length > setupSize) {
          throw new RuntimeException(s"Setup instructions (${setupInstructions.length}) exceed the maximum allowed length ($setupSize)")
        }
        val setupBeefCount = setupSize - setupInstructions.length
        val setupBeefFiller = Seq.fill(setupBeefCount)("0000BEEF")
        val haltCount = haltEndAddr - haltStartAddr
        val haltFiller = Seq.fill(haltCount)("E7FFFFFF")
        instructionHexStrings ++ userBeefFiller ++ setupInstructions ++ setupBeefFiller ++ haltFiller
    }
    raw.map { token =>
      val hex = token.trim.stripPrefix("0x").stripPrefix("0X").stripPrefix("h").stripPrefix("H")
      val value = java.lang.Long.parseLong(hex, 16) & 0xffffffffL
      f"$value%08x"
    }
  }
  val imemDepth = 1 << log2Ceil(imemWords.length.max(1))
  val imemPadded = imemWords.padTo(imemDepth, "0000beef")
  private val imemHexFile = new File("generated/imem_inline.hex")
  imemHexFile.getParentFile.mkdirs()
  private val imemWriter = new PrintWriter(imemHexFile)
  imemPadded.foreach(imemWriter.println)
  imemWriter.close()
  // Next PC is also the fetch address. Default holds PC, which is what a
  // memory stall does: the next instruction stays fetched and is not executed.
  val pcNext = Wire(UInt(32.W))
  pcNext := pc
  pc := pcNext
  val addrBits = log2Ceil(imemDepth).max(1)
  val fetchWord = Mux(reset.asBool,
    (0x80.U(32.W) >> 2)(addrBits - 1, 0),
    (pcNext >> 2)(addrBits - 1, 0))
  val romAddr = Wire(UInt(addrBits.W))
  romAddr := fetchWord
  val romOverlayEn = WireDefault(false.B)
  val romOverlayData = WireDefault(0.U(32.W))
  val instruction = Wire(UInt(32.W))
  if (chiselRom) {
    val rom = Module(new ChiselInstrRom(imemPadded, addrBits))
    rom.io.addr := romAddr
    rom.io.overlayEn := romOverlayEn
    rom.io.overlayData := romOverlayData
    instruction := rom.io.data
  } else {
    val instructionRom = Module(new InstrRom(imemDepth, addrBits, imemHexFile.getAbsolutePath))
    instructionRom.io.clk := clock
    instructionRom.io.addr := romAddr
    instructionRom.io.overlayEn := romOverlayEn
    instructionRom.io.overlayData := romOverlayData
    instruction := instructionRom.io.data
  }

  // A body fetch or a sector word stalls the instruction. The ROM word
  // at that PC is not executed. The overlay loads the ROM register the
  // cycle before the fetched word runs.
  val stallFetch = WireDefault(false.B)
  val startFetch = WireDefault(false.B)

  // Instruction decode
  val format = instruction(31, 28)
  val a = instruction(27, 24)  // Register a
  val b = instruction(23, 20)  // Register b
  val op = instruction(19, 16) // Opcode
  val c_reg = instruction(3, 0) // Register c (for F0 format)
  val imm = instruction(15, 0) // Immediate value (for F1 format)
  val off = instruction(23, 0) // Branch offset (for F3 format)
  val cond = instruction(27, 24) // Branch condition (for F3 format)
  val memOffset = instruction(19, 0) // Memory offset (for F2 format)
  
  // Extract register fields for accessing the register file
  val regA = a
  val regB = b
  val regC = c_reg
  
  // Determine instruction type
  val isBranch = format(3, 2) === "b11".U
  val isMemory = format(3, 2) === "b10".U
  val isF1Format = format(3, 2) === "b01".U  // For immediate operations
  
  // Branch subtypes
  val isBranchToReg = format(3, 1) === "b110".U  // Branch to register (BT R)
  val isBranchWithOffset = format(3, 1) === "b111".U  // Branch with offset
  
  // Memory access parameters
  val isLoad = isMemory && !format(1)  // u=0 for load
  val isStore = isMemory && format(1)  // u=1 for store
  val isByte = isMemory && format(0)   // v=1 for byte

  // One read port. All 16 registers stay. No instruction reads three.
  // A store reads Rb, then Ra. An F0 operation other than MOV H reads Rb,
  // then Rc. MOV H, an immediate, a load, and a branch read at most one.
  // The first of a pair is latched. PC stays until the second read commits.
  val regLatched = RegInit(false.B)
  val regCaptured = Reg(UInt(32.W))
  val heldInsn = Reg(UInt(32.W))
  val isF0 = format(3, 2) === "b00".U
  val readsB = isMemory || (isF0 && op =/= 0.U) || (isF1Format && op =/= 0.U)
  val readsX = isStore || isBranchToReg || (isF0 && !((format === "b0010".U) && (op === 0.U)))
  val twoRead = readsB && readsX
  // Phases 1..16 copy the register file into the snapshot block, through
  // the one read port. 17 plants the link and branches to 0x20. 18
  // presents snapshot word 0. 19..34 write the registers back, Ra
  // replaced by the result. The handler runs with phase 0.
  val fpPhase = RegInit(0.U(6.W))
  val fpSaving = fpPhase >= 1.U && fpPhase <= 16.U
  val fpSnapAddr = WireDefault(0.U(4.W))
  val fpSnapWe = WireDefault(false.B)
  val fpSnapWdata = WireDefault(0.U(32.W))
  val fpSnapRdata = Wire(UInt(32.W))
  val fpFinish = WireDefault(false.B)
  if (chiselRom) {
    val snap = Module(new ChiselFpSnap)
    snap.io.addr := fpSnapAddr
    snap.io.we := fpSnapWe
    snap.io.wdata := fpSnapWdata
    fpSnapRdata := snap.io.rdata
  } else {
    val snap = Module(new FpSnap)
    snap.io.clk := clock
    snap.io.addr := fpSnapAddr
    snap.io.we := fpSnapWe
    snap.io.wdata := fpSnapWdata
    fpSnapRdata := snap.io.rdata
  }
  val readAddr = WireDefault(regB)
  when (regLatched) {
    readAddr := Mux(isStore, regA, regC)
  } .elsewhen (readsB) {
    readAddr := regB
  } .otherwise {
    readAddr := Mux(isStore, regA, regC)
  }
  when (fpSaving) {
    readAddr := (fpPhase - 1.U)(3, 0)
  }
  val rdPort = regs(readAddr)
  val rdB = Mux(regLatched, regCaptured, rdPort)
  val rdX = rdPort
  
  // By default, increment PC
  val nextPC = pc + 4.U
  
  // Default signal values
  val regWrite = WireDefault(false.B)
  val regWriteAddr = WireDefault(0.U(4.W))  // 4 bits for 16 registers
  val regWriteData = WireDefault(0.U(32.W))
  
  // Memory interface signals
  io.memAddr := 0.U
  io.memWriteData := 0.U
  io.memWrite := false.B
  io.memRead := false.B
  io.memByte := false.B
  io.screenWe := false.B
  io.screenBit := false.B
  io.bmpData := 0.U
  io.bmpWord := 0.U
  io.armed := armed
  io.statusWe := false.B
  io.statusWord := 0.U

  // Logger boilerplate
  io.messageCode := 0.U
  io.trigger := false.B
  
  // Flag to track if CPU should halt (for simulation purposes)
  val halted = RegInit(false.B)
  
  // LED state register for memory-mapped LED control
  val ledState = RegInit(false.B)

  // Proof 6. The SPI window is -48/-44. Only the placed-body image has
  // it, so the other elaborations keep the memory path they already had.
  val spi = if (bodyFetch) {
    val mod = Module(new SpiSector)
    mod.io.write := false.B
    mod.io.ctrl := false.B
    mod.io.wdata := 0.U
    mod.io.sectorBase := 0.U
    mod.io.norWord := 0.U
    mod.io.norDone := false.B
    Some(mod)
  } else None
  // -72 is the bootstrap's word port: a store sets the flash address, a
  // load reads one word and adds 4. -68 is the sector base SpiSector adds
  // its word index to. Both sit under the book's window, which starts at
  // -64, and above the screen word at -80. -84 is the status register,
  // the next word under -80. -76 stays reserved and is not decoded.
  // -96 is the trapped Rb, -92 is the trapped Rc, and a store to -88
  // writes the floating-point result and returns from the trap.
  // -64 is the millisecond counter. The SD window stays -48/-44.
  val norPtr = if (flashBoot) RegInit(0.U(24.W)) else 0.U(24.W)
  val sectorBase = if (diskBoot) RegInit(0.U(24.W)) else 0.U(24.W)
  val norPending = if (flashBoot) RegInit(false.B) else false.B
  val norKick = if (flashBoot) WireDefault(false.B) else false.B
  val nor = if (flashBoot) Some(Module(new SpiNor(half = 4))) else None
  if (flashBoot) {
    val eng = nor.get
    eng.io.start := false.B
    eng.io.addr := 0.U
    eng.io.miso := io.spiMiso
    io.spiCsN := eng.io.csN
    io.spiClk := eng.io.sclk
    io.spiMosi := eng.io.mosi
    spi.get.io.sectorBase := sectorBase
    spi.get.io.norWord := eng.io.word
  }
  if (uartDisk) {
    spi.get.io.sectorBase := sectorBase
  }
  val uartPending = if (uartDisk) RegInit(false.B) else false.B
  // Dock picture RAM is written by the pixel clock. The store address is
  // a sum, so the arrival cycle's early pixel edge stores word 0.
  // Phase 0 latches the word after that sum has settled. Phase 1 writes
  // the latch. Phase 2 keeps the latch on the pins while the enable is
  // low, then the PC moves.
  val bmpPhase = if (uartDisk) RegInit(0.U(2.W)) else 0.U(2.W)
  val bmpWordR = if (uartDisk) Reg(UInt(13.W)) else 0.U(13.W)
  val spiLoad = if (bodyFetch) RegInit(false.B) else false.B
  val spiLoadCtrl = if (bodyFetch) RegInit(false.B) else false.B
  if (bodyFetch) {
    spiLoad := false.B
  }
  // A load of -64 completes from the counter below, not from RAM.
  // A load of -60 completes from the switch bit, on the same cycle.
  // A load of -40 is the mouse word. A load of -36 is the keyboard byte.
  val timerLoad = RegInit(false.B)
  val btnLoad = RegInit(false.B)
  val msLoad = RegInit(false.B)
  val kbdLoad = RegInit(false.B)
  // The picture RAM is written by the store and read by the video.
  // That RAM has no CPU read port. The 4K shadow is 1024 words on this
  // clock, written in the same cycle as screenWe. Twelve CPU-clock
  // write clocks drag the Dock off the DDR3 write and the CPU leaves
  // the boot ROM, so the Dock read uses the picture's pixel-clock
  // blocks. The request stays up until the ack rises, and the next
  // instruction waits until the ack falls, so it cannot take the
  // previous word. A word past the depth reads as 0. The execute path
  // does not hold the PC.
  val bmpDepth = if (uartDisk) 6144 else 1024
  val bmpAddrW = log2Ceil(bmpDepth)
  val bmpRdAddr = Wire(UInt(bmpAddrW.W))
  val bmpRdEn = if (!uartDisk) WireDefault(false.B) else false.B
  bmpRdAddr := 0.U
  val bmpRdHit = RegInit(false.B)
  val bmpLoad = RegInit(false.B)
  val bmpRdSt = if (uartDisk) RegInit(0.U(2.W)) else 0.U(2.W)
  val bmpAddrHold = if (uartDisk) Reg(UInt(13.W)) else 0.U(13.W)
  val bmpHitHold = if (uartDisk) RegInit(false.B) else false.B
  val ackMeta = if (uartDisk) RegInit(false.B) else false.B
  val ackSync = if (uartDisk) RegInit(false.B) else false.B
  if (uartDisk) {
    ackMeta := io.bmpRdAck
    ackSync := ackMeta
    io.bmpRdAddr := bmpAddrHold
    io.bmpRdReq := (bmpRdSt === 1.U) && bmpHitHold
  } else {
    io.bmpRdAddr := 0.U
    io.bmpRdReq := false.B
  }
  val bmpRdData = if (!uartDisk) {
    val bmpMem = SyncReadMem(bmpDepth, UInt(32.W))
    when (io.screenWe && (io.bmpWord < bmpDepth.U)) {
      bmpMem.write(io.bmpWord(bmpAddrW - 1, 0), io.bmpData)
    }
    bmpMem.read(bmpRdAddr, bmpRdEn)
  } else {
    io.bmpRdData
  }
  timerLoad := false.B
  btnLoad := false.B
  msLoad := false.B
  kbdLoad := false.B
  bmpLoad := false.B
  bmpRdHit := false.B
  // Book's millisecond counter. Step 2, limit 27000: exactly 13500
  // clocks at 13.5 MHz. The Dock limit 48375 is 24187.5 clocks at
  // 24.1875 MHz, alternating 24188 and 24187, exact over every 2 ms.
  val msPhaseLimit = if (uartDisk) 48375 else 27000
  val msPhase = RegInit(0.U(16.W))
  val msec = RegInit(0.U(32.W))
  val msSum = msPhase + 2.U
  when (msSum >= msPhaseLimit.U) {
    msPhase := msSum - msPhaseLimit.U
    msec := msec + 1.U
  } .otherwise {
    msPhase := msSum
  }

  // H is the high word of a product, or the remainder of a division.
  // MOV Ra, H (F0, u=1, op MOV) reads it. DIV is one restoring step
  // per clock, then a sign fix, on this adder. A combinational divider
  // does not fit the Nano 4K. MUL is the registered multiply above:
  // the issue cycle presents the operands, and the next cycle writes
  // the low word to Ra and the high word to H. u=0 sign-extends, which
  // is the book's MUL. u=1 zero-extends, which is UMUL. C and V stay.
  // N and Z follow Ra.
  val hReg = RegInit(0.U(32.W))
  val hwMul = Module(new HwMul)
  hwMul.io.clk := clock
  hwMul.io.x := 0.U(33.W)
  hwMul.io.y := 0.U(33.W)
  val mulPhase = RegInit(0.U(1.W))
  val mulDest = Reg(UInt(4.W))
  val divPhase = RegInit(0.U(6.W))
  val divQuot = RegInit(0.U(32.W))
  val divRem = RegInit(0.U(32.W))
  val divDen = RegInit(0.U(32.W))
  val divDest = RegInit(0.U(4.W))
  val divNegD = RegInit(false.B)
  val divNegS = RegInit(false.B)
  val divNegQ = RegInit(false.B)
  val divNegR = RegInit(false.B)
  val divAdjust = RegInit(false.B)
  val divFix = RegInit(false.B)
  val divLhs = WireDefault(0.U(32.W))
  val divRhs = WireDefault(0.U(32.W))
  val divSub = WireDefault(true.B)
  val divRhsEff = Mux(divSub, (~divRhs).asUInt, divRhs)
  val divSum = Cat(0.U(1.W), divLhs) + Cat(0.U(1.W), divRhsEff) + Mux(divSub, 1.U(33.W), 0.U(33.W))
  val divDiff = divSum(31, 0)
  val divGe = divSum(32)

  // FAD, FSB, FML and FDV copy the registers into the snapshot block
  // and branch to MT[0]. The Oberon trap reads Rb and Rc from -96 and
  // -92. A store of the result to -88 writes the snapshot back, one
  // register a cycle, with Ra replaced and H restored. N and Z follow
  // the result. C and V stay. The phase counter is next to the read port.
  val fpRa = Reg(UInt(4.W))
  val fpRbVal = Reg(UInt(32.W))
  val fpRcVal = Reg(UInt(32.W))
  val fpResult = Reg(UInt(32.W))
  val fpReturn = Reg(UInt(32.W))
  val fpSavedH = Reg(UInt(32.W))
  val fpSavedC = RegInit(false.B)
  val fpSavedV = RegInit(false.B)
  val fpRbLoad = RegInit(false.B)
  val fpRcLoad = RegInit(false.B)
  val fpHold = WireDefault(false.B)
  fpRbLoad := false.B
  fpRcLoad := false.B

  // Extra cycle of a two-read. PC stays on this instruction until the
  // second read commits. A stall owns the cycle instead.
  val regHold = twoRead && !regLatched && !stallFetch &&
    !memoryAccessPending && divPhase === 0.U && mulPhase === 0.U &&
    fpPhase === 0.U && !reset.asBool && !halted

  // Proof 5. Page 0x22 is the placed Blink5 body. A fetch of that page
  // reads external memory. Every other PC, including reset and the
  // loader, keeps the pROM. The word is overlaid into the ROM register
  // the cycle before it executes, which is the same register the
  // one-address fetch uses. A load or store already in flight keeps the
  // memory port; the next instruction is fetched after it completes.
  val bodyWord = if (bodyFetch) Reg(UInt(32.W)) else 0.U(32.W)
  val bodyFor = if (bodyFetch) Reg(UInt(32.W)) else 0.U(32.W)
  val bodyReady = if (bodyFetch) RegInit(false.B) else false.B
  val bodyPhase = if (bodyFetch) RegInit(0.U(2.W)) else 0.U(2.W)
  // The ROM is only the bootstrap. The trap, the copied core, and the
  // placed body are fetched from external memory. ROM[0] is the first
  // bootstrap word, so an address below 0x80 must not fall through to it.
  // Sector reads on the Dock share the DDR3 port with instruction fetch.
  // Phase 0 idle, 1 address captured, 2 read in flight, 3 deliver.
  val secPhase = if (uartDisk) RegInit(0.U(2.W)) else 0.U(2.W)
  val secAddr = if (uartDisk) Reg(UInt(32.W)) else 0.U(32.W)
  val secWordR = if (uartDisk) Reg(UInt(32.W)) else 0.U(32.W)
  val inBody = if (bodyFetch) {
    !(pc >= 0x80.U && pc < core.get.stubEnd.U)
  } else false.B
  val haveBody = if (bodyFetch) bodyReady && pc === bodyFor else false.B
  // Steal the memory port for one sector word before the next fetch.
  val secSteal = if (uartDisk) {
    secPhase === 1.U && bodyPhase === 0.U && !memoryAccessPending &&
      divPhase === 0.U && mulPhase === 0.U && fpPhase === 0.U && !haveBody
  } else false.B
  val secHold = if (uartDisk) {
    secPhase =/= 0.U && !haveBody && !memoryAccessPending &&
      divPhase === 0.U && mulPhase === 0.U
  } else false.B
  val wantBody = if (bodyFetch) {
    inBody && !haveBody && !memoryAccessPending && divPhase === 0.U &&
      mulPhase === 0.U && fpPhase === 0.U && !secHold
  } else false.B
  if (bodyFetch) {
    when (wantBody) {
      when (bodyPhase === 0.U) {
        startFetch := true.B
        bodyPhase := 1.U
      } .elsewhen (bodyPhase === 1.U && !io.memStall) {
        bodyWord := io.memReadData
        bodyPhase := 2.U
      } .elsewhen (bodyPhase === 2.U) {
        bodyPhase := 0.U
        bodyReady := true.B
        bodyFor := pc
      }
    } .elsewhen (haveBody && !regHold) {
      // The overlay is in the ROM register for this cycle only. A later
      // branch back to the same PC, the trap vector included, has to
      // fetch again. Leaving bodyReady set made the second BLR to
      // MT[0] execute ROM[0] and re-enter the stub. A two-read hold
      // still needs this word on the commit cycle.
      bodyReady := false.B
    } .elsewhen (!inBody) {
      bodyPhase := 0.U
    }
    when (wantBody) {
      stallFetch := true.B
    }
    if (uartDisk) {
      // A sector word is in flight. One ready instruction may retire.
      // The next fetch waits so it does not share the DDR3 port.
      // A store that is still retiring keeps the port; the read waits.
      when (secHold) {
        stallFetch := true.B
      }
    }
  }

  // Main execution state machine.
  // A pending load completes when memStall is low. Block RAM ties memStall
  // to 0, so this is still the original one-cycle load. Extra stall cycles
  // re-fetch the next instruction and do not execute it.
  when (stallFetch) {
    // The ROM word at this PC is a hold. Do not execute it. The state
    // machine above owns the HyperRAM read. pcNext stays on this PC.
    when (if (uartDisk) secSteal else false.B) {
      io.memAddr := secAddr
      io.memRead := true.B
    } .elsewhen (startFetch) {
      io.memAddr := pc
      io.memRead := true.B
    }
  } .elsewhen (memoryAccessPending) {
    // A -72 load owns the NOR for many cycles. HyperRAM is not in that
    // transfer, so memStall stays low and must not complete the load.
    val norHold = if (flashBoot) norPending else false.B
    val uartHold = if (uartDisk) uartPending else false.B
    if (flashBoot) {
      when (norPending && nor.get.io.done) {
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := nor.get.io.word
        memoryAccessPending := false.B
        norPending := false.B
        norPtr := norPtr + 4.U
        printf(p"NOR word ${Hexadecimal(nor.get.io.word)} next ${Hexadecimal(norPtr + 4.U)}\n")
      }
    }
    if (uartDisk) {
      when (uartPending && io.diskValid) {
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := io.diskWord
        memoryAccessPending := false.B
        uartPending := false.B
        io.diskTake := true.B
      }
    }
    if (uartDisk) {
      // 1 waits for the ack. 2 waits for it to fall. The register
      // write is the rising ack. The next instruction starts after
      // the fall, so a following load cannot reuse this word.
      when (bmpRdSt =/= 0.U) {
        when (bmpRdSt === 1.U && !bmpHitHold) {
          regWrite := true.B
          regWriteAddr := memoryTargetReg
          regWriteData := 0.U
          bmpRdSt := 0.U
          memoryAccessPending := false.B
          printf(p"Bitmap R${memoryTargetReg} ${Hexadecimal(0.U)}\n")
        } .elsewhen (bmpRdSt === 1.U && ackSync) {
          regWrite := true.B
          regWriteAddr := memoryTargetReg
          regWriteData := io.bmpRdData
          bmpRdSt := 2.U
          memoryAccessPending := true.B
          printf(p"Bitmap R${memoryTargetReg} ${Hexadecimal(io.bmpRdData)}\n")
        } .elsewhen (bmpRdSt === 2.U && !ackSync) {
          bmpRdSt := 0.U
          memoryAccessPending := false.B
        } .otherwise {
          memoryAccessPending := true.B
        }
      }
    }
    when (timerLoad) {
      when (memoryIsLoad) {
        val timerByte = MuxLookup(memoryLane, msec(7, 0))(Seq(
          0.U -> msec(7, 0),
          1.U -> msec(15, 8),
          2.U -> msec(23, 16),
          3.U -> msec(31, 24)
        ))
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := Mux(memoryIsByte, Cat(0.U(24.W), timerByte), msec)
        printf(p"Timer R${memoryTargetReg} ${Hexadecimal(msec)}\n")
      }
      memoryAccessPending := false.B
    } .elsewhen (btnLoad) {
      when (memoryIsLoad) {
        // RISC5Top reads -60 as {20'b0, buttons, switches}. Switch 0
        // is bit 0. This board's key, and the UART press, are that bit.
        val btnWord = Cat(0.U(31.W), io.btnPressed)
        val btnByte = MuxLookup(memoryLane, btnWord(7, 0))(Seq(
          0.U -> btnWord(7, 0),
          1.U -> btnWord(15, 8),
          2.U -> btnWord(23, 16),
          3.U -> btnWord(31, 24)
        ))
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := Mux(memoryIsByte, Cat(0.U(24.W), btnByte), btnWord)
        printf(p"Keys R${memoryTargetReg} ${Hexadecimal(btnWord)}\n")
      }
      memoryAccessPending := false.B
    } .elsewhen (msLoad) {
      when (memoryIsLoad) {
        // Input.Mouse and SYSTEM.BIT read -40. Bit 28 is keyboard-ready.
        // Bits 26:24 are the buttons, 21:12 are Y, 9:0 are X. Nothing is
        // wired, so the good image is zero. The dark image is ones.
        val msWord = Mux(io.kbdOnes, "hFFFFFFFF".U(32.W), 0.U(32.W))
        val msByte = MuxLookup(memoryLane, msWord(7, 0))(Seq(
          0.U -> msWord(7, 0),
          1.U -> msWord(15, 8),
          2.U -> msWord(23, 16),
          3.U -> msWord(31, 24)
        ))
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := Mux(memoryIsByte, Cat(0.U(24.W), msByte), msWord)
        printf(p"Mouse R${memoryTargetReg} ${Hexadecimal(msWord)}\n")
      }
      memoryAccessPending := false.B
    } .elsewhen (kbdLoad) {
      when (memoryIsLoad) {
        // Input.Peek reads -36 only when bit 28 of -40 is set. The byte
        // is 0. A read acknowledges the keyboard; nothing is pending.
        val kbdWord = 0.U(32.W)
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := Mux(memoryIsByte, 0.U, kbdWord)
        printf(p"Kbd R${memoryTargetReg} ${Hexadecimal(kbdWord)}\n")
      }
      memoryAccessPending := false.B
    } .elsewhen (bmpLoad) {
      when (memoryIsLoad) {
        val word = Mux(bmpRdHit, bmpRdData, 0.U)
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := word
        printf(p"Bitmap R${memoryTargetReg} ${Hexadecimal(word)}\n")
      }
      memoryAccessPending := false.B
    } .elsewhen (fpRbLoad) {
      when (memoryIsLoad) {
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := fpRbVal
        printf(p"FP Rb R${memoryTargetReg} ${Hexadecimal(fpRbVal)}\n")
      }
      memoryAccessPending := false.B
    } .elsewhen (fpRcLoad) {
      when (memoryIsLoad) {
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := fpRcVal
        printf(p"FP Rc R${memoryTargetReg} ${Hexadecimal(fpRcVal)}\n")
      }
      memoryAccessPending := false.B
    } .elsewhen (!norHold && !uartHold && !io.memStall && bmpRdSt === 0.U) {
      when (memoryIsLoad) {
        // RISC5 inbus1: LDB zero-extends the lane adr[1:0] selects.
        // LDW returns the word. Same completion cycle either way.
        val loadedMem = io.memReadData
        val loaded = if (bodyFetch) {
          Mux(spiLoad, Mux(spiLoadCtrl, spi.get.io.cdata, spi.get.io.rdata), loadedMem)
        } else {
          loadedMem
        }
        val loadedByte = MuxLookup(memoryLane, loaded(7, 0))(Seq(
          0.U -> loaded(7, 0),
          1.U -> loaded(15, 8),
          2.U -> loaded(23, 16),
          3.U -> loaded(31, 24)
        ))
        regWrite := true.B
        regWriteAddr := memoryTargetReg
        regWriteData := Mux(memoryIsByte, Cat(0.U(24.W), loadedByte), loaded)
        printf(p"Load complete R${memoryTargetReg} byte=${memoryIsByte} lane=${memoryLane} word=${loaded}\n")
      }
      memoryAccessPending := false.B
    }
  } .elsewhen (divPhase =/= 0.U) {
    // Phase 1..2 take absolute values. 3..34 are the 32 restoring steps.
    // 35..36 apply the toward-zero signs. 37..38 are Oberon's floor
    // adjustment when the divisor is positive and the remainder is negative.
    when (divPhase === 1.U) {
      when (divNegD) {
        divLhs := 0.U
        divRhs := divQuot
        divQuot := divDiff
      }
      divPhase := 2.U
    } .elsewhen (divPhase === 2.U) {
      when (divNegS) {
        divLhs := 0.U
        divRhs := divDen
        divDen := divDiff
      }
      divPhase := 3.U
    } .elsewhen (divPhase <= 34.U) {
      val rShift = Cat(divRem(30, 0), divQuot(31))
      divLhs := rShift
      divRhs := divDen
      divRem := Mux(divGe, divDiff, rShift)
      divQuot := Cat(divQuot(30, 0), divGe)
      divPhase := divPhase + 1.U
    } .elsewhen (divPhase === 35.U) {
      when (divNegQ) {
        divLhs := 0.U
        divRhs := divQuot
        divQuot := divDiff
      }
      divPhase := 36.U
    } .elsewhen (divPhase === 36.U) {
      val nextRem = Mux(divNegR, divDiff, divRem)
      when (divNegR) {
        divLhs := 0.U
        divRhs := divRem
      }
      divRem := nextRem
      divFix := divAdjust && nextRem(31)
      divPhase := 37.U
    } .elsewhen (divPhase === 37.U) {
      when (divFix) {
        divLhs := divQuot
        divRhs := 1.U
        divQuot := divDiff
      }
      divPhase := 38.U
    } .elsewhen (divPhase === 38.U) {
      val nextRem = Mux(divFix, divDiff, divRem)
      when (divFix) {
        divLhs := divRem
        divRhs := divDen
        divSub := false.B
      }
      hReg := nextRem
      regWrite := true.B
      regWriteAddr := divDest
      regWriteData := divQuot
      divPhase := 0.U
      pcNext := nextPC
      printf(p"DIV done R${divDest}=${divQuot} H=${nextRem}\n")
    } .otherwise {
      divPhase := 0.U
    }
  } .elsewhen (mulPhase =/= 0.U) {
    // The product register captured the multiply on the issue cycle.
    hReg := hwMul.io.p(63, 32)
    regWrite := true.B
    regWriteAddr := mulDest
    regWriteData := hwMul.io.p(31, 0)
    mulPhase := 0.U
    pcNext := nextPC
    printf(p"MUL done R${mulDest}=${hwMul.io.p(31, 0)} H=${hwMul.io.p(63, 32)}\n")
  } .elsewhen (fpPhase =/= 0.U) {
    when (fpSaving) {
      // The read port is this register. The block captures it on the clock.
      fpSnapWe := true.B
      fpSnapAddr := (fpPhase - 1.U)(3, 0)
      fpSnapWdata := rdPort
      fpPhase := fpPhase + 1.U
      pcNext := pc
    } .elsewhen (fpPhase === 17.U) {
      // The block already holds the pre-trap R15. The handler reads the link.
      regs(15) := fpReturn
      pcNext := 0x20.U
      fpPhase := 0.U
      printf(p"FP trap enter R15=${Hexadecimal(fpReturn)} -> 20\n")
    } .elsewhen (fpPhase === 18.U) {
      // The word is on the output after this clock.
      fpSnapAddr := 0.U
      fpPhase := 19.U
      pcNext := pc
    } .otherwise {
      val idx = (fpPhase - 19.U)(3, 0)
      regWrite := true.B
      regWriteAddr := idx
      regWriteData := Mux(idx === fpRa, fpResult, fpSnapRdata)
      when (fpPhase =/= 34.U) {
        fpSnapAddr := (idx + 1.U)(3, 0)
      }
      when (fpPhase === 34.U) {
        fpFinish := true.B
        pcNext := fpReturn
        fpPhase := 0.U
        printf(p"FP done R${fpRa}=${Hexadecimal(fpResult)} pc ${Hexadecimal(fpReturn)}\n")
      } .otherwise {
        fpPhase := fpPhase + 1.U
        pcNext := pc
      }
    }
  } .elsewhen (regHold) {
    // Rb is on the read port. The second read commits next cycle.
    pcNext := pc
  } .elsewhen (isBranch) {
    // Check for halt instruction (branch self with e7ffffff)
    when (instruction === "hE7FFFFFF".U) {
      halted := true.B
      printf(p"Halt instruction detected (e7ffffff), halting CPU\n")
    } .otherwise {
      // Handle branch instructions (F3 format)
      val takeBranch = Wire(Bool())
      takeBranch := false.B
      
      // RISC5.v: cond = IR[27] xor the low condition. IR[27] is cond(3).
      val cc = cond(2, 0)
      val sflag = n ^ v
      val ccTrue = MuxLookup(cc, false.B)(Seq(
        0.U -> n,             // MI / PL
        1.U -> z,             // EQ / NE
        2.U -> c,             // CS / CC
        3.U -> v,             // VS / VC
        4.U -> (c || z),      // LS / HI
        5.U -> sflag,         // LT / GE
        6.U -> (sflag || z),  // LE / GT
        7.U -> true.B         // always / never
      ))
      takeBranch := cond(3) ^ ccTrue
      
      when (takeBranch) {
        // ISA: v=1 (format bit 0) is BL — plant LNK, then jump.
        // Do not use the regWrite path: that would also update N/Z.
        when (format(0)) {
          regs(15) := pc + 4.U
          printf(p"BL: R15 = ${pc + 4.U} (PC+4)\n")
          printf(p"Writing ${pc + 4.U} to register 15 (R15 = ${pc + 4.U})\n")
        }
        // Check if this is a branch to register or branch with offset based on format bits
        when (isBranchToReg) {
          // Branch to register: Use register c as the branch target
          val targetReg = c_reg
          
          // Make sure the low 2 bits are 0 (word-aligned).
          // isStore is false here, so port X is Rc.
          pcNext := rdX & ~(3.U(32.W))
          
          // Debug output for branch to register
          printf(p"BT R$targetReg: Branching to address ${rdX & ~(3.U(32.W))} vs ${rdX}\n")
        } .elsewhen (isBranchWithOffset) {
          // Calculate branch target address: PC + 4 + off * 4
          // For a 24-bit signed offset, extend sign to 32 bits
          val signedOff = Cat(Fill(8, off(23)), off)
          pcNext := pc + 4.U + (signedOff << 2)
          
          // Debug output for branch with offset
          printf(p"Branch with offset: PC + 4 + (${signedOff} << 2) = ${pc + 4.U + (signedOff << 2)}\n")
        } .otherwise {
          // Invalid branch format
          printf(p"WARNING: Invalid branch format detected: ${format}\n")
          pcNext := nextPC
        }
      } .otherwise {
        pcNext := nextPC
      }
    }
  } .elsewhen (isMemory) {
    // F2 Format: Memory access instructions
    // Calculate effective address: reg(b) + offset
    // Sign-extend the offset to 32 bits
    val signExtOffset = Cat(Fill(12, memOffset(19)), memOffset)
    val effectiveAddr = rdB + signExtOffset
    // -48 is 0xFFFFFFD0 and -44 is 0xFFFFFFD4. Bit 2 picks the register.
    val spiHit = if (bodyFetch) {
      effectiveAddr(31, 3) === "h1FFFFFFA".U(29.W) && effectiveAddr(1, 0) === 0.U
    } else {
      false.B
    }
    // -72 (0xFFFFFFB8) is one NOR or UART word. -68 (0xFFFFFFBC) is the
    // sector base. -64 is the millisecond counter. -60 is the switches.
    val norPtrHit = if (flashBoot) effectiveAddr === "hFFFFFFB8".U else false.B
    val uartHit = if (uartDisk) effectiveAddr === "hFFFFFFB8".U else false.B
    val norBaseHit = if (diskBoot) effectiveAddr === "hFFFFFFBC".U else false.B
    // 0xFFFE0000, 64 KB. The low half is the 4K bitmap and the high
    // half is the Dock bitmap. Blink stores both. This image keeps one.
    val bmpRegion = !isByte && effectiveAddr(31, 16) === "hFFFE".U
    val bmpLive = if (uartDisk) effectiveAddr(15) else !effectiveAddr(15)
    // -80. Dropped. The bitmap replaced the one block.
    val screenHit = !isByte && effectiveAddr === "hFFFFFFB0".U
    // -84. Bits 0-7 are the status byte. Bit 8 is the screen mode.
    // Dropped on every image. The video module holds the nine flops.
    val statusHit = !isByte && effectiveAddr === "hFFFFFFAC".U
    // -64 (0xFFFFFFC0). Kernel.Time loads the millisecond counter.
    val timerAddr = effectiveAddr === "hFFFFFFC0".U
    // -60 (0xFFFFFFC4). The book's switches. Bit 0 is the button.
    val btnAddr = effectiveAddr === "hFFFFFFC4".U
    // -40 (0xFFFFFFD8). Mouse, and keyboard-ready in bit 28.
    val msAddr = effectiveAddr(31, 2) === "h3FFFFFF6".U
    // -36 (0xFFFFFFDC). The keyboard byte. A read acknowledges it.
    val kbdAddr = effectiveAddr(31, 2) === "h3FFFFFF7".U
    // -96 Rb, -92 Rc, -88 the result store that returns from the trap.
    val fpRbAddr = !isByte && effectiveAddr === "hFFFFFFA0".U
    val fpRcAddr = !isByte && effectiveAddr === "hFFFFFFA4".U
    val fpWrAddr = !isByte && effectiveAddr === "hFFFFFFA8".U

    when (isLoad) {  // LDW and LDB. The byte extract is on the completion cycle.
        val useHyper = WireDefault(true.B)
        when (timerAddr) {
          useHyper := false.B
          timerLoad := true.B
          memoryAccessPending := true.B
          memoryIsLoad := true.B
          memoryIsByte := isByte
          memoryLane := effectiveAddr(1, 0)
          memoryTargetReg := regA
        }
        when (btnAddr) {
          useHyper := false.B
          btnLoad := true.B
          memoryAccessPending := true.B
          memoryIsLoad := true.B
          memoryIsByte := isByte
          memoryLane := effectiveAddr(1, 0)
          memoryTargetReg := regA
        }
        when (msAddr) {
          useHyper := false.B
          msLoad := true.B
          memoryAccessPending := true.B
          memoryIsLoad := true.B
          memoryIsByte := isByte
          memoryLane := effectiveAddr(1, 0)
          memoryTargetReg := regA
        }
        when (kbdAddr) {
          useHyper := false.B
          kbdLoad := true.B
          memoryAccessPending := true.B
          memoryIsLoad := true.B
          memoryIsByte := isByte
          memoryLane := effectiveAddr(1, 0)
          memoryTargetReg := regA
        }
        when (fpRbAddr) {
          useHyper := false.B
          fpRbLoad := true.B
          memoryAccessPending := true.B
          memoryIsLoad := true.B
          memoryIsByte := false.B
          memoryLane := 0.U
          memoryTargetReg := regA
        }
        when (fpRcAddr) {
          useHyper := false.B
          fpRcLoad := true.B
          memoryAccessPending := true.B
          memoryIsLoad := true.B
          memoryIsByte := false.B
          memoryLane := 0.U
          memoryTargetReg := regA
        }
        if (bodyFetch) {
          when (spiHit) {
            useHyper := false.B
            spiLoad := true.B
            spiLoadCtrl := effectiveAddr(2)
            memoryAccessPending := true.B
            memoryIsLoad := true.B
            memoryIsByte := false.B
            memoryLane := 0.U
            memoryTargetReg := regA
          }
        }
        if (flashBoot) {
          when (norPtrHit) {
            useHyper := false.B
            norPending := true.B
            norKick := true.B
            memoryAccessPending := true.B
            memoryIsLoad := true.B
            memoryIsByte := false.B
            memoryLane := 0.U
            memoryTargetReg := regA
          }
        }
        if (uartDisk) {
          when (uartHit) {
            useHyper := false.B
            uartPending := true.B
            memoryAccessPending := true.B
            memoryIsLoad := true.B
            memoryIsByte := false.B
            memoryLane := 0.U
            memoryTargetReg := regA
          }
        }
        when (bmpRegion && bmpLive) {
          val word = effectiveAddr(14, 2)
          if (uartDisk) {
            bmpAddrHold := word
            bmpHitHold := word < bmpDepth.U
            bmpRdSt := 1.U
          } else {
            bmpRdAddr := word(bmpAddrW - 1, 0)
            bmpRdEn := word < bmpDepth.U
            bmpRdHit := word < bmpDepth.U
            bmpLoad := true.B
          }
          useHyper := false.B
          memoryAccessPending := true.B
          memoryIsLoad := true.B
          memoryIsByte := false.B
          memoryLane := 0.U
          memoryTargetReg := regA
        }
        when (useHyper) {
          io.memAddr := effectiveAddr
          io.memRead := true.B
          io.memByte := isByte
          memoryAccessPending := true.B
          memoryIsLoad := true.B
          memoryIsByte := isByte
          memoryLane := effectiveAddr(1, 0)
          memoryTargetReg := regA
          printf(p"Load start ${effectiveAddr} -> R${regA} byte=${isByte}\n")
        }
    } .otherwise {  // Store instructions
      when (if (bodyFetch) spiHit else false.B) {
        if (bodyFetch) {
          spi.get.io.write := true.B
          spi.get.io.ctrl := effectiveAddr(2)
          spi.get.io.wdata := rdX
        }
        memoryIsLoad := false.B
        memoryIsByte := false.B
        memoryAccessPending := waitForStores.B
      } .elsewhen (statusHit) {
        io.statusWe := true.B
        io.statusWord := rdX(8, 0)
      } .elsewhen (bmpRegion) {
        when (bmpLive) {
          if (uartDisk) {
            when (bmpPhase === 0.U) {
              bmpWordR := effectiveAddr(14, 2)
              bmpPhase := 1.U
            } .elsewhen (bmpPhase === 1.U) {
              io.screenWe := true.B
              io.screenBit := rdX(0)
              io.bmpData := rdX
              io.bmpWord := bmpWordR
              bmpPhase := 2.U
            } .otherwise {
              io.screenBit := rdX(0)
              io.bmpData := rdX
              io.bmpWord := bmpWordR
              bmpPhase := 0.U
            }
          } else {
            io.screenWe := true.B
            io.screenBit := rdX(0)
            io.bmpData := rdX
            io.bmpWord := effectiveAddr(14, 2)
          }
        }
      } .elsewhen (fpWrAddr) {
        fpResult := rdX
        fpPhase := 18.U
        fpHold := true.B
        printf(p"FP result ${Hexadecimal(rdX)} -> R${fpRa}\n")
      } .elsewhen (screenHit || timerAddr || btnAddr || msAddr || kbdAddr) {
        // -80 is the old one-block screen. -64's write is blank in
        // the book. -60's write is the LED bank. -40 and -36 are read.
        // This board's blink pin is the armed light, not that bank, so
        // none of these stores goes to memory.
      } .elsewhen (if (diskBoot) norPtrHit || uartHit || norBaseHit else false.B) {
        if (flashBoot) {
          when (norPtrHit) {
            norPtr := rdX(23, 0)
          }
        }
        if (diskBoot) {
          when (norBaseHit) {
            sectorBase := rdX(23, 0)
          }
        }
      } .elsewhen (!isByte) {  // STW - Store Word
        // Start a memory write operation
        io.memAddr := effectiveAddr
        io.memWriteData := rdX
        io.memWrite := true.B

        // Blink stores `light` at the address the linker records.
        val lightHit = if (splitFetch) effectiveAddr === core.get.light.U else false.B
        when (lightHit) {
          ledState := rdX(0)
          Logger.log(io, Logger.Codes.LedToggle, ledState.asUInt)
          printf(p"Memory-mapped LED write detected at address ${effectiveAddr}: Setting LED to ${rdX(0)}\n")
        }
        
        // Debug output
        printf(p"STW: Storing R${regA}(${rdX}) to address ${effectiveAddr}\n")
        
        // Block RAM returns in the same cycle. HyperRAM waits out Tcmd.
        memoryIsLoad := false.B
        memoryIsByte := false.B
        memoryAccessPending := waitForStores.B
        if (useArm) {
          when (effectiveAddr === armAddrC.U(32.W)) {
            printf(p"ARM ${Hexadecimal(rdX)} hit=${rdX === BigInt(armWordC).U(32.W)}\n")
            when (rdX === BigInt(armWordC).U(32.W)) {
              armed := true.B
            }
          }
        }
      } .otherwise {
        // STB. RISC5 outbus puts A[7:0] in the lane and zeros the other
        // three bytes of the bus. The bridge's data_mask is what keeps the
        // neighbours. A full-word write here would fail the lane test.
        val lane = effectiveAddr(1, 0)
        val low = rdX(7, 0)
        val placed = MuxLookup(lane, Cat(0.U(24.W), low))(Seq(
          0.U -> Cat(0.U(24.W), low),
          1.U -> Cat(0.U(16.W), low, 0.U(8.W)),
          2.U -> Cat(0.U(8.W), low, 0.U(16.W)),
          3.U -> Cat(low, 0.U(24.W))
        ))
        io.memAddr := effectiveAddr
        io.memWriteData := placed
        io.memWrite := true.B
        io.memByte := true.B
        memoryIsLoad := false.B
        memoryIsByte := true.B
        memoryLane := lane
        memoryAccessPending := waitForStores.B
        printf(p"STB: R${regA} byte ${low} lane ${lane} address ${effectiveAddr}\n")
      }
    }
    
    // For memory operations, we only advance PC after completing the operation.
    // A code-window ROM read holds the PC so the data word is not executed.
    when (!memoryAccessPending) {
      // Phase 2 is the cycle after the write. The PC stays through the
      // write so the address the pixel clock samples cannot change.
      // A load is not a write. Holding its PC made the same LDW run
      // again after R0 became 0, and the second read was address 0.
      val bmpStall = if (uartDisk) {
        !isLoad && bmpRegion && bmpLive && bmpPhase =/= 2.U
      } else {
        false.B
      }
      when (!bmpStall) {
        pcNext := nextPC
      }
    }
    when (fpHold) {
      pcNext := pc
    }
  } .elsewhen (isF1Format || (format(3, 2) === "b00".U)) {
    // Unified handling for immediate (F1) and register (F0) operations
    // Determine if we are using the immediate operand (F1) or register operand (F0).
    val useImmediate = isF1Format
    // F1 v=1 sign-extends the 16-bit immediate (ORG.Put1 when im < 0).
    // v=0 zero-extends, which is what every existing blink immediate uses.
    val imm32 = Mux(format(0), Cat(Fill(16, imm(15)), imm), Cat(0.U(16.W), imm))
    val operand = Mux(useImmediate, imm32, rdX)
    val shamt = operand(4, 0)
    val bval = rdB
    // One 5-stage barrel for LSL, ASR and ROR. Three Verilog shifts did not
    // fit the GW1NSR-4C (4992 logic cells, limit 4608). A shift of 0 leaves
    // the register unchanged because no stage is selected.
    val shiftRight = (op === 2.U) || (op === 3.U)
    val shiftRotate = op === 3.U
    val shiftResult = (0 until 5).foldLeft(bval) { (cur, i) =>
      val amt = 1 << i
      val wrapped = cur(amt - 1, 0)
      val rightFill = Mux(shiftRotate, wrapped, Fill(amt, bval(31)))
      val righted = Cat(rightFill, cur(31, amt))
      val lefted = Cat(cur(31 - amt, 0), 0.U(amt.W))
      Mux(shamt(i), Mux(shiftRight, righted, lefted), cur)
    }

    when (!useImmediate && (op >= 12.U)) {
      // F0 FAD, FSB, FML, FDV. The block copies the registers while PC
      // stays here. The link is planted when that copy finishes, then
      // MT[0] runs the branch Kernel.Init planted at 0x20.
      fpRa := regA
      fpRbVal := rdB
      fpRcVal := rdX
      fpReturn := pc + 4.U
      fpSavedH := hReg
      fpSavedC := c
      fpSavedV := v
      fpPhase := 1.U
      pcNext := pc
      printf(p"FP trap op ${op} R${regA} := R${regB} op R${regC} -> 20\n")
    } .otherwise {
    switch(op) {
      is(0.U) { // MOV - Move immediate value to register / MHI special-case
        when(useImmediate && ((format === "b0110".U) || (format === "b0111".U))) {
          // MHI. ORG.Put1(Mov+U) is 0110. The v bit is also set when the
          // 32-bit constant is negative, because Put1 adds V for im < 0.
          // Both encodings are the 16-bit field shifted up, not a
          // sign-extended MOV and not MOV NZCV.
          regWrite := true.B
          regWriteAddr := regA
          regWriteData := imm << 16
          printf(p"MHI: R$regA = ${imm} << 16 = ${imm << 16}\n")
        } .elsewhen(!useImmediate && (format === "b0010".U)) {
          // F0 u=1, op MOV. ORG.H and the MOD arm: Ra = H. v is 0.
          regWrite := true.B
          regWriteAddr := regA
          regWriteData := hReg
          z := hReg === 0.U
          n := hReg(31)
          printf(p"MOV H: R$regA = ${hReg}\n")
          pcNext := nextPC
        } .otherwise {
          regWrite := true.B
          regWriteAddr := regA
          regWriteData := operand
          
          // Debug output for MOV
          printf(p"MOV: R$regA = ${operand}\n")
        }
        
        // Set flags
        z := operand === 0.U
        n := operand(31)
        
        // IMPORTANT: After executing the instruction, update the PC.
        pcNext := nextPC
      }
      
      is(6.U) { // IOR - Bitwise OR with immediate/register operand
        val result = bval | operand
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
        
        // Debug output for IOR
        printf(p"IOR: R$regA = R$regB(${bval}) | ${operand} = $result\n")
        
        // IMPORTANT: After executing the instruction, update the PC.
        pcNext := nextPC
      }
      
      is(7.U) { // XOR - Exclusive OR with immediate/register operand
        val result = bval ^ operand
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
        
        // IMPORTANT: After executing the instruction, update the PC.
        pcNext := nextPC
      }
      
      is(8.U) { // ADD - Add immediate/register operand
        val result = bval + operand
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        val sa = result(31)
        val sb = bval(31)
        val sc = operand(31)
        // RISC5.v cx/vv for ADD.
        c := (!sb && sc && !sa) || (sb && sc && sa) || (sb && !sa)
        v := (sa && !sb && !sc) || (!sa && sb && sc)
        
        n := result(31)
        z := result === 0.U
        
        // Debug output for ADD
        printf(p"ADD: R$regA = R$regB(${bval}) + ${operand} = $result\n")
        
        // IMPORTANT: After executing the instruction, update the PC.
        pcNext := nextPC
      }
      
      is(9.U) { // SUB - Subtract immediate/register operand
        val result = bval - operand
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        val sa = result(31)
        val sb = bval(31)
        val sc = operand(31)
        // RISC5.v cx/vv for SUB. sa is the result sign, sb is Rb, sc is the operand.
        c := (!sb && sc && !sa) || (sb && sc && sa) || (!sb && sa)
        v := (sa && !sb && sc) || (!sa && sb && !sc)
        
        n := result(31)
        z := result === 0.U
        
        when(!useImmediate) {
          printf(p"F0 SUB: R$regB(${bval}) - R$regC(${rdX}) = $result, Z=$z\n")
        } .otherwise {
          printf(p"SUB: R$regB(${bval}) - ${imm} = $result\n")
        }
        
        pcNext := nextPC
      }

      is(1.U) { // LSL
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := shiftResult
        pcNext := nextPC
      }
      is(2.U) { // ASR
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := shiftResult
        pcNext := nextPC
      }
      is(3.U) { // ROR
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := shiftResult
        pcNext := nextPC
      }
      is(4.U) { // AND
        val result = bval & operand
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        pcNext := nextPC
      }
      is(5.U) { // ANN  Ra = Rb & ~operand
        val result = bval & (~operand)
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        pcNext := nextPC
      }
      is(10.U) { // MUL. Low word in Ra, high word in H, one cycle later.
        val signed = !format(1)
        val sx = Mux(signed && bval(31), 1.U(1.W), 0.U(1.W))
        val sy = Mux(signed && operand(31), 1.U(1.W), 0.U(1.W))
        hwMul.io.x := Cat(sx, bval)
        hwMul.io.y := Cat(sy, operand)
        mulDest := regA
        mulPhase := 1.U
        printf(p"MUL: R$regB=${bval} * ${operand} -> R$regA signed=$signed\n")
      }
      is(11.U) { // DIV. Quotient in Ra, remainder in H. PC holds until phase 38.
        val unsigned = format(1)
        divQuot := bval
        divRem := 0.U
        divDen := operand
        divDest := regA
        divNegD := bval(31) && !unsigned
        divNegS := operand(31) && !unsigned
        divNegQ := (bval(31) ^ operand(31)) && !unsigned
        divNegR := bval(31) && !unsigned
        divAdjust := !unsigned && !operand(31) && (operand =/= 0.U)
        divFix := false.B
        divPhase := 1.U
        printf(p"DIV: R$regB=${bval} / ${operand} -> R$regA\n")
      }
    }
    }
  } .otherwise {
    // For any other format (not implemented), just increment PC
    pcNext := nextPC
  }

  if (bodyFetch) {
    // The overlay is captured by the ROM's output register, so it is
    // driven the cycle before the body word executes.
    when (wantBody && bodyPhase === 2.U) {
      romOverlayEn := true.B
      romOverlayData := bodyWord
    }
  }
  if (diskBoot) {
    // Bootstrap words sit at ROM index 0. The core is not in this ROM.
    romAddr := ((pcNext - 0x80.U) >> 2)(addrBits - 1, 0)
  }
  // While reset is 1 the ROM must present the instruction at 0x80.
  // The compiled image stores that word at index 0.
  when (reset.asBool) {
    romAddr := (if (splitFetch) 0.U(addrBits.W) else (0x80.U(32.W) >> 2)(addrBits - 1, 0))
  }

  if (flashBoot) {
    val eng = nor.get
    when (!eng.io.busy) {
      when (norKick) {
        eng.io.start := true.B
        eng.io.addr := norPtr
      } .elsewhen (spi.get.io.norStart) {
        eng.io.start := true.B
        eng.io.addr := spi.get.io.norAddr
      }
    }
    // A bootstrap load owns the returning word. The sector side only
    // sees a completion when it asked for one.
    spi.get.io.norDone := eng.io.done && !norPending
  }

  if (uartDisk) {
    // The sector word is a DDR3 read on the same port as a body fetch.
    // norStart is one cycle. The read is issued once the port is free.
    when (secPhase === 0.U && spi.get.io.norStart) {
      secAddr := spi.get.io.norAddr
      secPhase := 1.U
    }
    when (secSteal) {
      secPhase := 2.U
    }
    when (secPhase === 2.U && !io.memStall) {
      secWordR := io.memReadData
      secPhase := 3.U
    }
    when (secPhase === 3.U) {
      spi.get.io.norWord := secWordR
      spi.get.io.norDone := true.B
      secPhase := 0.U
    }
  }

  // Latch the first operand and keep this instruction word. The commit
  // cycle clears the latch. A stall after the latch replays the word.
  when (regHold) {
    regCaptured := rdPort
    heldInsn := instruction
    regLatched := true.B
  } .elsewhen (!stallFetch && !memoryAccessPending && divPhase === 0.U &&
      mulPhase === 0.U && fpPhase === 0.U && !reset.asBool) {
    regLatched := false.B
  }
  when (regHold || (regLatched && stallFetch)) {
    romOverlayEn := true.B
    romOverlayData := Mux(regHold, instruction, heldInsn)
  }

  // Register write logic
  when (regWrite) {
    regs(regWriteAddr) := regWriteData
    
    // Set flags
    n := regWriteData(31)  // Negative flag from result MSB
    z := regWriteData === 0.U  // Zero flag if result is zero
    
    // Debug output
    printf(p"Writing ${regWriteData} to register ${regWriteAddr} (R${regWriteAddr} = ${regWriteData})\n")
  }
  // The restore writes a register every cycle, and that write also
  // drives N and Z. The trapped result is what N and Z keep.
  when (fpFinish) {
    n := fpResult(31)
    z := fpResult === 0.U
    c := fpSavedC
    v := fpSavedV
    hReg := fpSavedH
  }
  
  // Halt when the PC runs off the ROM. A disk-boot fetch from outside
  // the bootstrap is inBody, and that word comes from external memory.
  val pastRom = (pc >> 2) >= imemWords.length.U
  when (pastRom && !inBody) {
    halted := true.B
  }
  
  // Debug output for each instruction
  printf(p"PC: ${pc}, Instruction: ${Hexadecimal(instruction)}\n")
  printf(p"Format: ${format}, A: ${a}, B: ${b}, OP: ${op}, IMM: ${imm}\n")
  
  // Debug output: register and flag content
  printf(p"R0: ${regs(0)}, R1: ${regs(1)}, R2: ${regs(2)}, R3: ${regs(3)}, R4: ${regs(4)}, R5: ${regs(5)}, R6: ${regs(6)}, R7: ${regs(7)}, R8: ${regs(8)}, R9: ${regs(9)}, R10: ${regs(10)}, R11: ${regs(11)}, R12: ${regs(12)}, R13: ${regs(13)}, R14: ${regs(14)}, R15: ${regs(15)}, Z: ${z}\n")
  
  // Connect outputs (we only export R0-R3 to not overwhelm the available ports on the FPGAs)
  io.r0 := regs(0)
  io.r1 := regs(1)
  io.r2 := regs(2)
  io.r3 := regs(3)
  io.r4 := regs(4)
  io.r5 := regs(5)
  io.r7 := regs(7)
  io.r8 := regs(8)
  io.r9 := regs(9)
  io.dbgMask := (
    if (useArm) Mux(armed, ((BigInt(1) << 40) - 1).U(40.W), 0.U(40.W))
    else 0.U(40.W)
  )
  io.halted := halted
  val ledReady = if (useArm) ledState && armed else ledState
  io.led := ledReady
  io.pc := pc  // Connect the program counter to the output
}

object CPUSubset0 {
  // Get project root using environment variable or marker file
  private def getProjectRoot(): String = {
    Option(System.getenv("CHISEL_CPU_PROJECT_ROOT")).getOrElse {
      // Attempt to find project root by looking for a marker file/directory
      var current = new File(sys.props("user.dir"))
      while (current != null &&
             !new File(current, "build.sc").exists() &&
             !new File(current, "build.mill").exists()) {
        current = current.getParentFile
      }
      if (current != null) current.getAbsolutePath
      else sys.props("user.dir")
    }
  }

  // Load instructions from a code file
  def loadInstructionsFromFile(filePath: String): Seq[String] = {
    try {
      val source = scala.io.Source.fromFile(filePath)
      val instructions = source.getLines()
        .map(_.trim)
        .filter(_.nonEmpty)
        .map(line => line.stripPrefix("0x"))
        .toSeq
      source.close()
      println(s"Successfully loaded ${instructions.length} instructions from $filePath")
      instructions
    } catch {
      case e: Exception =>
        println(s"Error loading instructions from $filePath: ${e.getMessage}")
        e.printStackTrace()
        // Return empty sequence if file can't be loaded
        Seq.empty[String]
    }
  }

  def main(args: Array[String]): Unit = {
    println("Generating CPUSubset0 Verilog")
    
    val targetDir = "generated"
    val outputFile = "CPUSubset0.v"
    val topOutputFile = "CPUMinimalWrapper.v"
    
    new java.io.File(targetDir).mkdirs()
    
    // Get project root
    val projectRoot = getProjectRoot()

    // The 4K boots from the NOR disk. The Dock boots from the same file
    // sent over the UART into DDR3. Both ROMs are the bootstrap.
    val fpgaImage = sys.env.getOrElse("FPGA_IMAGE", "modules")
    val modules = fpgaImage == "modules"
    val ddr3modules = fpgaImage == "ddr3modules"
    if (!modules && !ddr3modules) {
      throw new RuntimeException(
        s"FPGA_IMAGE=$fpgaImage is retired. Use modules or ddr3modules."
      )
    }
    val ddr3 = ddr3modules
    val hyper = modules
    val imemArg = sys.env.getOrElse(
      "BLINK3_IMEM",
      if (ddr3modules) "sim/visualizer/imem/ddr3modules.words"
      else "sim/visualizer/imem/modules.words"
    )
    val imemFile = new File(imemArg)
    val imemPath =
      if (imemFile.isAbsolute) imemFile.getAbsolutePath
      else new File(projectRoot, imemArg).getAbsolutePath
    val words = loadInstructionsFromFile(imemPath)
    if (words.isEmpty) {
      throw new RuntimeException(
        s"disk bootstrap empty at $imemPath — run sim/link_inner.py"
      )
    }
    val imageName = if (ddr3modules) "Primer 20K UART disk" else "Nano 4K NOR disk"
    println(s"FPGA image: $imageName bootstrap ${words.length} words from $imemPath")
    val programInstructions = Seq.empty[String]
    val customMemoryImage = Some(words)

    val coreMap = Some(CoreMap.load(projectRoot).getOrElse(
      throw new RuntimeException(
        "disk boot needs sim/visualizer/imem/core.map — run sim/link_inner.py"
      )
    ))
    val useUart = ddr3modules && coreMap.exists(_.uartDisk)
    val useFlash = modules && coreMap.exists(_.romWords <= 512) && !coreMap.exists(_.uartDisk)
    // The dark image. A load of -40 is ones, so Input does not arm.
    val kbdOnes = sys.env.get("KBD_ONES").contains("1")
    if (kbdOnes) println("FPGA image: -40 reads ones")
    if (ddr3modules && !useUart) {
      throw new RuntimeException("ddr3modules needs the UART disk map")
    }
    if (modules && !useFlash) {
      throw new RuntimeException("modules needs the NOR disk map")
    }

    val firtoolOpts = Array(
      "-disable-all-randomization",
      "-strip-debug-info",
      "--lowering-options=disallowLocalVariables,disallowPackedArrays,noAlwaysComb"
    )
    
    // Generate the base CPU Verilog for testing and debugging
    val verilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUSubset0(
        programInstructions,
        customMemoryImage = customMemoryImage,
        waitForStores = hyper || ddr3,
        bodyFetch = true,
        core = coreMap,
        flashBoot = useFlash,
        uartDisk = useUart
      ),
      firtoolOpts = firtoolOpts
    )
    
    // Generate the top-level wrapper for FPGA synthesis (with real Gowin RAM)
    val topVerilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUMinimalWrapper(
        useRealGowin = true,
        programInstructions = programInstructions,
        customMemoryImage = customMemoryImage,
        memBackend = if (ddr3) "ddr3" else "hyperram",
        bodyFetch = true,
        core = coreMap,
        flashBoot = useFlash,
        uartDisk = useUart,
        enableLogger = ddr3,
        kbdOnes = kbdOnes
      ),
      firtoolOpts = firtoolOpts
    )
    
    // Generate a simulation-friendly version (with mock RAM / HyperRAM user model)
    val simVerilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUMinimalWrapper(
        useRealGowin = false,
        programInstructions = programInstructions,
        customMemoryImage = customMemoryImage,
        memBackend = if (ddr3) "ddr3" else "hyperram",
        bodyFetch = true,
        core = coreMap,
        flashBoot = useFlash,
        uartDisk = useUart,
        enableLogger = ddr3,
        kbdOnes = kbdOnes
      ),
      firtoolOpts = firtoolOpts
    )
    
    // Write the simulation version
    val simWriter = new java.io.PrintWriter(new java.io.File(s"$targetDir/CPUMinimalWrapper_sim.v"))
    simWriter.write(simVerilogCode)
    simWriter.close()
    
    // Write both Verilog files
    val writer = new java.io.PrintWriter(new java.io.File(s"$targetDir/$outputFile"))
    writer.write(verilogCode)
    writer.close()
    
    val topWriter = new java.io.PrintWriter(new java.io.File(s"$targetDir/$topOutputFile"))
    topWriter.write(topVerilogCode)
    topWriter.close()
    
    println(s"Verilog written to $targetDir/$outputFile")
    println(s"Top-level wrapper written to $targetDir/$topOutputFile")
    println(s"Simulation wrapper written to $targetDir/CPUMinimalWrapper_sim.v")
    // Initialize the trace file
    // CPUSubset0Companion.initializeTraceWriter("default", traceDir)
  }
}

// Define a custom PrintWriter that writes to both a file and stdout
class TeePrintWriter(fileName: String) {
  private val file = new PrintWriter(new File(fileName))
  
  def printf(fmt: String, args: Any*): Unit = {
    val message = fmt.format(args: _*)
    Console.print(message)
    file.print(message)
    file.flush()
  }
  
  def close(): Unit = {
    file.close()
  }
}

// Create an object companion for CPUSubset0 to hold shared state
object CPUSubset0Companion {
  // Create a trace file writer for simulations
  private var _traceWriter: TeePrintWriter = _
  private var _currentTestId: String = "default"
  private var _traceDir: String = _
  
  def initializeTraceWriter(testId: String = "default", traceDirPath: String = null): Unit = {
    if (_traceWriter != null) {
      finalizeTraceWriter() // Close any existing writer
    }
    
    // Set the current test ID and trace directory
    _currentTestId = testId.replaceAll("[^a-zA-Z0-9_-]", "_") // Make filename-safe
    _traceDir = if (traceDirPath != null) traceDirPath else "trace"
    
    val traceDirFile = new java.io.File(_traceDir)
    
    if (!traceDirFile.exists()) {
      traceDirFile.mkdirs()
    }
    
    val traceFileName = new java.io.File(_traceDir, s"cpu_trace_${_currentTestId}.txt").getAbsolutePath
    
    _traceWriter = new TeePrintWriter(traceFileName)
    _traceWriter.printf("CPU Simulation Trace - Test ID: %s\n", _currentTestId)
    _traceWriter.printf("==================\n\n")
    _traceWriter.printf("Trace Output:\n")
    _traceWriter.printf("=============\n\n")
  }
  
  def finalizeTraceWriter(): Unit = {
    if (_traceWriter != null) {
      _traceWriter.close()
      _traceWriter = null
    }
  }
  
  def traceWriter: TeePrintWriter = {
    if (_traceWriter == null) {
      initializeTraceWriter()
    }
    _traceWriter
  }
  
  def currentTestId: String = _currentTestId
  
  def printTrace(msg: String): Unit = {
    if (_traceWriter == null) {
      initializeTraceWriter()
    }
    traceWriter.printf(msg)
  }
}
