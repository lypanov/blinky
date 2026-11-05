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
       |  reg [31:0] mem [0:${depth - 1}];
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

class CPUSubset0(instructionHexStrings: Seq[String] = Seq.empty[String],
                 customMemoryImage: Option[Seq[String]] = None,
                 waitForStores: Boolean = false,
                 requireMemCheck: Boolean = false,
                 extraChecks: Int = 0,
                 fetchStored: Boolean = false) extends Module {
  val io = IO(new Bundle {
    val r0 = Output(UInt(32.W))  // Output register R0 for testing
    val r1 = Output(UInt(32.W))  // Output register R1 for testing
    val r2 = Output(UInt(32.W))  // Output register R2 for testing
    val r3 = Output(UInt(32.W))  // Output register R3 for testing
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
  })
  
  // Initialize the logByte signal with a default value
  io.logByte := 0.U
  
  // Initialize PC: if a custom memory image is provided then start at 0x00 (for trampoline execution),
  // otherwise default to 0x80.
  val pc = RegInit(0x80.U(32.W))
  
  // Registers
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
  // HyperRAM prologue stores each compare-difference to 0x7C0+4*slot.
  // The LED follows Blink3 only after every one of those stores was zero.
  // extraChecks are the step-2 ALU compares plus, on the step-3 image, the
  // byte and .rsc header compares. Both live at 0x800+4*slot.
  val memSlots = if (requireMemCheck) 8 else 0
  val totalChecks = memSlots + extraChecks
  val checkMask = if (totalChecks > 0) Some(RegInit(0.U(totalChecks.W))) else None
  
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
  val instructionRom = Module(new InstrRom(imemDepth, addrBits, imemHexFile.getAbsolutePath))
  instructionRom.io.clk := clock
  instructionRom.io.addr := fetchWord
  val instruction = instructionRom.io.data

  // Step 4. One PC (0x1F00) executes the word HyperRAM returns for that
  // address, not the ROM word. The ROM word there is a hold. The fetch
  // stalls, captures the load, and on the next clock the ROM's output
  // register is loaded from that word. Every other PC keeps the ROM path.
  val fetching = RegInit(false.B)
  val inject = RegInit(false.B)
  val doneFetch = RegInit(false.B)
  val fetchedWord = Reg(UInt(32.W))
  val patchPC = 0x1F00.U
  val atPatch = pc === patchPC
  val stallFetch = WireDefault(false.B)
  val nextFetching = WireDefault(fetching)
  val nextInject = WireDefault(inject)
  val nextDone = WireDefault(doneFetch)
  val nextWord = WireDefault(fetchedWord)
  val startFetch = WireDefault(false.B)
  if (fetchStored) {
    stallFetch := atPatch && !doneFetch
    when (stallFetch) {
      when (!fetching && !inject) {
        startFetch := true.B
        nextFetching := true.B
      } .elsewhen (fetching && !io.memStall) {
        nextWord := io.memReadData
        nextFetching := false.B
        nextInject := true.B
      } .elsewhen (inject) {
        nextInject := false.B
        nextDone := true.B
      }
    } .elsewhen (!atPatch) {
      nextFetching := false.B
      nextInject := false.B
      nextDone := false.B
    }
    instructionRom.io.overlayEn := inject
  } else {
    instructionRom.io.overlayEn := false.B
  }
  instructionRom.io.overlayData := fetchedWord
  fetching := nextFetching
  inject := nextInject
  doneFetch := nextDone
  fetchedWord := nextWord
  
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

  // Logger boilerplate
  io.messageCode := 0.U
  io.trigger := false.B
  
  // Flag to track if CPU should halt (for simulation purposes)
  val halted = RegInit(false.B)
  
  // LED state register for memory-mapped LED control
  val ledState = RegInit(false.B)
  
  // Main execution state machine.
  // A pending load completes when memStall is low. Block RAM ties memStall
  // to 0, so this is still the original one-cycle load. Extra stall cycles
  // re-fetch the next instruction and do not execute it.
  when (stallFetch) {
    // The ROM word at this PC is a hold. Do not execute it. The state
    // machine above owns the HyperRAM read. pcNext stays on this PC.
    when (startFetch) {
      io.memAddr := patchPC
      io.memRead := true.B
    }
  } .elsewhen (memoryAccessPending) {
    when (!io.memStall) {
      when (memoryIsLoad) {
        // RISC5 inbus1: LDB zero-extends the lane adr[1:0] selects.
        // LDW returns the word. Same completion cycle either way.
        val loaded = io.memReadData
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
          
          // Make sure the low 2 bits are 0 (word-aligned)
          pcNext := regs(targetReg) & ~(3.U(32.W))
          
          // Debug output for branch to register
          printf(p"BT R$targetReg: Branching to address ${regs(targetReg) & ~(3.U(32.W))} vs ${regs(targetReg)}\n")
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
    val effectiveAddr = regs(regB) + signExtOffset
    
    when (isLoad) {  // LDW and LDB. The byte extract is on the completion cycle.
        io.memAddr := effectiveAddr
        io.memRead := true.B
        io.memByte := isByte
        memoryAccessPending := true.B
        memoryIsLoad := true.B
        memoryIsByte := isByte
        memoryLane := effectiveAddr(1, 0)
        memoryTargetReg := regA
        printf(p"Load start ${effectiveAddr} -> R${regA} byte=${isByte}\n")
    } .otherwise {  // Store instructions
      when (!isByte) {  // STW - Store Word
        // Start a memory write operation
        io.memAddr := effectiveAddr
        io.memWriteData := regs(regA)
        io.memWrite := true.B
        
        // LED MMIO: a68a501 snooped 0x10 (R13 hack). After 9d190e2, Blink2
        // stores `light` at the module variable block 0x50. Snoop both so
        // old 0x10 programs and the 0x50 map both drive io.led.
        when (effectiveAddr === 0x10.U || effectiveAddr === 0x50.U) {
          // Update LED state with bit 0 of the value being stored
          ledState := regs(regA)(0)
          // Use a single LED event code and pass the state as an extra 8-bit value.
          Logger.log(io, Logger.Codes.LedToggle, ledState.asUInt)
          // Debug output
          printf(p"Memory-mapped LED write detected at address ${effectiveAddr}: Setting LED to ${regs(regA)(0)}\n")
          CPUSubset0Companion.printTrace("Memory-mapped LED write detected (snoop 0x10 or 0x50)\n")
        }
        
        // Debug output
        printf(p"STW: Storing R${regA}(${regs(regA)}) to address ${effectiveAddr}\n")
        
        // Block RAM returns in the same cycle. HyperRAM waits out Tcmd.
        memoryIsLoad := false.B
        memoryIsByte := false.B
        memoryAccessPending := waitForStores.B
        // A store of zero at 0x7C0+4*slot arms one memory check.
        // Step 2 adds the same at 0x800+4*slot. Any missing zero keeps the LED dark.
        checkMask.foreach { mask =>
          when (regs(regA) === 0.U && effectiveAddr(1, 0) === 0.U) {
            val memDelta = effectiveAddr - 0x7C0.U
            when (memDelta < (memSlots * 4).U) {
              val slot = memDelta(4, 2)
              mask := mask | (1.U(totalChecks.W) << slot)
            }
            if (extraChecks > 0) {
              val aluDelta = effectiveAddr - 0x800.U
              when (aluDelta < (extraChecks * 4).U) {
                // Bit 7 of the byte offset is slot 32 (address 0x880). A
                // 5-bit index would wrap that store onto slot 0.
                val slot = aluDelta(8, 2) +& memSlots.U
                mask := mask | (1.U(totalChecks.W) << slot)
              }
            }
          }
        }
      } .otherwise {
        // STB. RISC5 outbus puts A[7:0] in the lane and zeros the other
        // three bytes of the bus. The bridge's data_mask is what keeps the
        // neighbours. A full-word write here would fail the lane test.
        val lane = effectiveAddr(1, 0)
        val low = regs(regA)(7, 0)
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
    
    // For memory operations, we only advance PC after completing the operation
    when (!memoryAccessPending) {
      pcNext := nextPC
    }
  } .elsewhen (isF1Format || (format(3, 2) === "b00".U)) {
    // Unified handling for immediate (F1) and register (F0) operations
    // Determine if we are using the immediate operand (F1) or register operand (F0).
    val useImmediate = isF1Format
    // F1 v=1 sign-extends the 16-bit immediate (ORG.Put1 when im < 0).
    // v=0 zero-extends, which is what every existing blink immediate uses.
    val imm32 = Mux(format(0), Cat(Fill(16, imm(15)), imm), Cat(0.U(16.W), imm))
    val operand = Mux(useImmediate, imm32, regs(regC))
    val shamt = operand(4, 0)
    val bval = regs(regB)
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

    switch(op) {
      is(0.U) { // MOV - Move immediate value to register / MHI special-case
        when(useImmediate && (format === "b0110".U)) {
          // Special case for MHI (Move High Immediate)
          // Encoding: 0111 a b 0000 imm
          regWrite := true.B
          regWriteAddr := regA
          regWriteData := imm << 16
          
          // Debug output for MHI
          printf(p"MHI: R$regA = ${imm} << 16 = ${imm << 16}\n")
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
        val result = regs(regB) | operand
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
        
        // Debug output for IOR
        printf(p"IOR: R$regA = R$regB(${regs(regB)}) | ${operand} = $result\n")
        
        // IMPORTANT: After executing the instruction, update the PC.
        pcNext := nextPC
      }
      
      is(7.U) { // XOR - Exclusive OR with immediate/register operand
        val result = regs(regB) ^ operand
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
        val result = regs(regB) + operand
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
        printf(p"ADD: R$regA = R$regB(${regs(regB)}) + ${operand} = $result\n")
        
        // IMPORTANT: After executing the instruction, update the PC.
        pcNext := nextPC
      }
      
      is(9.U) { // SUB - Subtract immediate/register operand
        val result = regs(regB) - operand
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
          printf(p"F0 SUB: R$regB(${regs(regB)}) - R$regC(${regs(regC)}) = $result, Z=$z\n")
        } .otherwise {
          printf(p"SUB: R$regB(${regs(regB)}) - ${imm} = $result\n")
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
    }
  } .otherwise {
    // For any other format (not implemented), just increment PC
    pcNext := nextPC
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
  
  // Special halt condition for simulation
  // We'll halt when pc points beyond our instruction memory
  when ((pc >> 2) >= imemWords.length.U) {
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
  io.halted := halted
  io.led := checkMask.map { m =>
    val armed = ((BigInt(1) << totalChecks) - 1).U(totalChecks.W)
    ledState && (m === armed)
  }.getOrElse(ledState)
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

    // Default FPGA image is Blink3 (linked LightToggle + AMMT, trampoline at 0).
    // FPGA_IMAGE=blink2 restores the old Blink2hw small-IMEM path.
    val fpgaImage = sys.env.getOrElse("FPGA_IMAGE", "blink3")
    val fixup = fpgaImage == "fixup"
    val rsc = fpgaImage == "rsc"
    val fetchbl = fpgaImage == "fetchbl"
    val hyper = fpgaImage == "hyperram" || fixup || rsc || fetchbl
    // 20 matches sim/build_fixup_imem.py. 32 matches sim/build_rsc_imem.py.
    // 34 matches sim/build_fetchbl_imem.py (those 32, plus the stored BL
    // and the link register). A mismatch leaves the LED dark, because a
    // slot that is never stored stays clear.
    val extra = if (fetchbl) 34 else if (rsc) 32 else if (fixup) 20 else 0
    val (programInstructions, customMemoryImage) = fpgaImage match {
      case "blink3" | "hyperram" | "fixup" | "rsc" | "fetchbl" =>
        val imemArg = sys.env.getOrElse("BLINK3_IMEM", "sim/visualizer/imem/blink3.words")
        val imemFile = new File(imemArg)
        val imemPath =
          if (imemFile.isAbsolute) imemFile.getAbsolutePath
          else new File(projectRoot, imemArg).getAbsolutePath
        val words = loadInstructionsFromFile(imemPath)
        if (words.isEmpty) {
          throw new RuntimeException(
            s"Blink3 IMEM empty at $imemPath — run sim/build_blink3_imem.py first"
          )
        }
        val imageName =
          if (fetchbl) "step-4 stored BL + HyperRAM"
          else if (rsc) "step-3 byte/.rsc reader + HyperRAM"
          else if (fixup) "fixup ALU + HyperRAM"
          else if (hyper) "HyperRAM prologue + Blink3"
          else "Blink3"
        println(s"FPGA image: $imageName custom IMEM ${words.length} words from $imemPath")
        (Seq.empty[String], Some(words))
      case _ =>
        val blink2hwCodePath = new File(projectRoot, "tests/Blink2hw.code").getAbsolutePath
        val programInstructions = loadInstructionsFromFile(blink2hwCodePath)
        println(s"FPGA image: Blink2hw ${programInstructions.length} instructions from $blink2hwCodePath")
        (programInstructions, None)
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
        waitForStores = hyper,
        requireMemCheck = hyper,
        extraChecks = extra,
        fetchStored = fetchbl
      ),
      firtoolOpts = firtoolOpts
    )
    
    // Generate the top-level wrapper for FPGA synthesis (with real Gowin RAM)
    val topVerilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUMinimalWrapper(
        useRealGowin = true,
        programInstructions = programInstructions,
        customMemoryImage = customMemoryImage,
        memBackend = if (hyper) "hyperram" else "blockram",
        extraChecks = extra,
        fetchStored = fetchbl
      ),
      firtoolOpts = firtoolOpts
    )
    
    // Generate a simulation-friendly version (with mock RAM / HyperRAM user model)
    val simVerilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUMinimalWrapper(
        useRealGowin = false,
        programInstructions = programInstructions,
        customMemoryImage = customMemoryImage,
        memBackend = if (hyper) "hyperram" else "blockram",
        extraChecks = extra,
        fetchStored = fetchbl
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
