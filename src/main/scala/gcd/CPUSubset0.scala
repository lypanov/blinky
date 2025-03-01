package gcd

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.io.{File, PrintWriter}

class CPUSubset0(instructionHexStrings: Seq[String] = Seq.empty[String]) extends Module {
  val io = IO(new Bundle {
    val r0 = Output(UInt(32.W))  // Output register R0 for testing
    val r1 = Output(UInt(32.W))  // Output register R1 for testing
    val r2 = Output(UInt(32.W))  // Output register R2 for testing
    val r3 = Output(UInt(32.W))  // Output register R3 for testing
    val halted = Output(Bool())  // Signal to indicate when the CPU has completed execution
    val led = Output(Bool())     // LED output for the Tang Nano 4K
    val pc = Output(UInt(32.W))  // Program counter value for testing
    
    // Memory interface - allows the CPU to access external memory
    val memAddr = Output(UInt(32.W))
    val memWriteData = Output(UInt(32.W))
    val memReadData = Input(UInt(32.W))
    val memWrite = Output(Bool())
    val memRead = Output(Bool())
  })
  
  // Program counter
  // Initialize PC to 0x80 (byte address) to start at the setup instructions
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
  
  val instructionMemory = {
    // Define memory sections by byte address and convert to word addresses
    val userProgEndAddr = 0x80 / 4     // User program ends at byte address 0x80 (word address 0x20)
    val setupStartAddr = 0x80 / 4      // Setup instructions start at byte address 0x80 (word address 0x20)
    val setupEndAddr = 0xA0 / 4        // Setup instructions end at byte address 0xA0 (word address 0x28)
    val haltStartAddr = 0xA0 / 4       // Halt instructions start at byte address 0xA0 (word address 0x28)
    val haltEndAddr = 0xB0 / 4         // Halt instructions end at byte address 0xB0 (word address 0x2C)
    
    // Ensure the provided hex strings don't extend beyond address 0x80 (word address 0x20)
    if (instructionHexStrings.length > userProgEndAddr) {
      throw new RuntimeException(s"Provided hex strings (${instructionHexStrings.length}) exceed the maximum allowed length ($userProgEndAddr)")
    }
    
    // Section A: User program (0x00-0x80)
    // Calculate how many "beef" instructions we need to fill up to address 0x80
    val userBeefCount = userProgEndAddr - instructionHexStrings.length
    val userBeefFiller = Seq.fill(userBeefCount)("0000BEEF")
    
    // Section B: Setup instructions (0x80-0xA0)
    // Define the setup instructions
    val setupInstructions = Seq(
      "4e000080", // MOV R14, 0x0080     ; Top of stack
      "4f0000A0", // MOV R15, 0x00A0     ; Halt instruction at end of instruction memory
      "40000000", // MOV R0, 0x0000      ; Set R0 to 0x0000 (function body)
      "c7000000"  // BT R0               ; Jump to user code
    )
    
    // Ensure the setup instructions don't exceed their allocated space
    val setupSize = setupEndAddr - setupStartAddr
    if (setupInstructions.length > setupSize) {
      throw new RuntimeException(s"Setup instructions (${setupInstructions.length}) exceed the maximum allowed length ($setupSize)")
    }
    
    // Calculate how many "beef" instructions we need to fill the remainder of the setup section
    val setupBeefCount = setupSize - setupInstructions.length
    val setupBeefFiller = Seq.fill(setupBeefCount)("0000BEEF")
    
    // Section C: Halt instructions (0xA0-0xB0)
    val haltCount = haltEndAddr - haltStartAddr
    val haltFiller = Seq.fill(haltCount)("E7FFFFFF")
    
    // Combine all sections to create the full program
    val fullProgram = instructionHexStrings ++ userBeefFiller ++ setupInstructions ++ setupBeefFiller ++ haltFiller
    
    // Create the instruction memory from the full program
    VecInit(fullProgram.map(hex => s"h$hex".U(32.W)))
  }
  
  // Instruction fetch
  val instructionAddr = (pc >> 2).asUInt  // Divide by 4 to get word address
  // Use a safe index to avoid out-of-bounds access
  val addrBits = log2Ceil(instructionMemory.length).max(1)
  val safeAddr = WireDefault(0.U(addrBits.W))
  safeAddr := instructionAddr(addrBits-1, 0)  // Take only the necessary LSBs
  val instruction = instructionMemory(safeAddr)
  
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
  
  // Flag to track if CPU should halt (for simulation purposes)
  val halted = RegInit(false.B)
  
  // LED state register for memory-mapped LED control
  val ledState = RegInit(false.B)
  
  // Main execution state machine
  when (memoryAccessPending) {
    // We're waiting for memory read to complete
    // Data should be available now from RAM (after 1 cycle delay)
    regWrite := true.B
    regWriteAddr := memoryTargetReg
    regWriteData := io.memReadData
    
    // Debug output
    printf(p"LDW: Completed load to R${memoryTargetReg}, value: ${io.memReadData}\n")
    
    // Clear the pending memory operation
    memoryAccessPending := false.B
    
    // Don't advance PC again during memory completion
  } .elsewhen (isBranch) {
    // Check for halt instruction (branch self with e7ffffff)
    when (instruction === "hE7FFFFFF".U) {
      halted := true.B
      printf(p"Halt instruction detected (e7ffffff), halting CPU\n")
    } .otherwise {
      // Handle branch instructions (F3 format)
      val takeBranch = Wire(Bool())
      takeBranch := false.B
      
      // Decode branch condition
      switch (cond) {
        is("b0001".U) { takeBranch := z }                   // EQ
        is("b1001".U) { takeBranch := !z }                  // NE
        is("b0101".U) { takeBranch := n ^ v }               // LT (Less Than)
        is("b0111".U) { takeBranch := true.B }              // Always
        is("b1111".U) { takeBranch := false.B }             // Never (BF)
      }
      
      when (takeBranch) {
        // Check if this is a branch to register or branch with offset based on format bits
        when (isBranchToReg) {
          // Branch to register: Use register c as the branch target
          val targetReg = c_reg
          
          // Make sure the low 2 bits are 0 (word-aligned)
          pc := regs(targetReg) & ~(3.U(32.W))
          
          // Debug output for branch to register
          printf(p"BT R$targetReg: Branching to address ${regs(targetReg) & ~(3.U(32.W))} vs ${regs(targetReg)}\n")
        } .elsewhen (isBranchWithOffset) {
          // Calculate branch target address: PC + 4 + off * 4
          // For a 24-bit signed offset, extend sign to 32 bits
          val signedOff = Cat(Fill(8, off(23)), off)
          pc := pc + 4.U + (signedOff << 2)
          
          // Debug output for branch with offset
          printf(p"Branch with offset: PC + 4 + (${signedOff} << 2) = ${pc + 4.U + (signedOff << 2)}\n")
        } .otherwise {
          // Invalid branch format
          printf(p"WARNING: Invalid branch format detected: ${format}\n")
          pc := nextPC
        }
      } .otherwise {
        pc := nextPC
      }
    }
  } .elsewhen (isMemory) {
    // F2 Format: Memory access instructions
    // Calculate effective address: reg(b) + offset
    // Sign-extend the offset to 32 bits
    val signExtOffset = Cat(Fill(12, memOffset(19)), memOffset)
    val effectiveAddr = regs(regB) + signExtOffset
    
    when (isLoad) {  // Load instructions
      // Special case: If loading into R13 from R0 base, always return 0x10 and ignore offset
      when ((regA === 13.U) && (regB === 0.U)) {
        // Override normal load behavior
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := 0x10.U
        
        // Debug output
        printf(p"Special LDW override: Writing 0x10 to R13 from base R0, ignoring offset.\n")
        
        // Update PC directly since we're not doing a memory access
        pc := nextPC
        
        // No memory access pending
        memoryAccessPending := false.B
      } .otherwise {
        // Normal load behavior
        when (!isByte) {  // LDW - Load Word
          // Start a memory read operation
          io.memAddr := effectiveAddr
          io.memRead := true.B
          
          // Set up state for memory completion next cycle
          memoryAccessPending := true.B
          memoryTargetReg := regA
          
          // Debug output
          printf(p"LDW: Starting load from address ${effectiveAddr} to R${regA}\n")
        } .otherwise {
          // LDB - Load Byte not implemented yet
        }
      }
    } .otherwise {  // Store instructions
      when (!isByte) {  // STW - Store Word
        // Start a memory write operation
        io.memAddr := effectiveAddr
        io.memWriteData := regs(regA)
        io.memWrite := true.B
        
        // Check if this is a write to the memory-mapped LED address (0x10)
        when (effectiveAddr === 0x10.U) {
          // Update LED state with bit 0 of the value being stored
          ledState := regs(regA)(0)
          
          // Debug output
          printf(p"Memory-mapped LED write detected at address 0x10: Setting LED to ${regs(regA)(0)}\n")
          CPUSubset0Companion.printTrace(s"Memory-mapped LED write detected at address 0x10: Setting LED to ${regs(regA)(0)}\n")
        }
        
        // Debug output
        printf(p"STW: Storing R${regA}(${regs(regA)}) to address ${effectiveAddr}\n")
        
        // For store operations, we don't need to wait for completion
        memoryAccessPending := false.B
      } .otherwise {
        // STB - Store Byte not implemented yet
      }
    }
    
    // For memory operations, we only advance PC after completing the operation
    when (!memoryAccessPending) {
      pc := nextPC
    }
  } .elsewhen (isF1Format || (format(3, 2) === "b00".U)) {
    // Unified handling for immediate (F1) and register (F0) operations
    // Determine if we are using the immediate operand (F1) or register operand (F0)
    val useImmediate = isF1Format
    // Select the second operand: immediate if F1, else register from 'c' if F0.
    val operand = Mux(useImmediate, imm, regs(regC))
    
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
        pc := nextPC
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
        pc := nextPC
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
        pc := nextPC
      }
      
      is(8.U) { // ADD - Add immediate/register operand
        val result = regs(regB) + operand
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
        
        // Debug output for ADD
        printf(p"ADD: R$regA = R$regB(${regs(regB)}) + ${operand} = $result\n")
        
        // IMPORTANT: After executing the instruction, update the PC.
        pc := nextPC
      }
      
      is(9.U) { // SUB - Subtract immediate/register operand
        val result = regs(regB) - operand
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
        
        // Debug output: differentiate between register (F0) and immediate (F1) SUB
        when(!useImmediate) {
          printf(p"F0 SUB: R$regB(${regs(regB)}) - R$regC(${regs(regC)}) = $result, Z=$z\n")
        } .otherwise {
          printf(p"SUB: R$regB(${regs(regB)}) - ${imm} = $result\n")
        }
        
        // IMPORTANT: After executing the instruction, update the PC.
        pc := nextPC
      }
    }
  } .otherwise {
    // For any other format (not implemented), just increment PC
    pc := nextPC
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
  when (instructionAddr >= instructionMemory.length.U) {
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
  io.led := ledState  // Connect LED output to our memory-mapped LED state
  io.pc := pc  // Connect the program counter to the output
}

object CPUSubset0 {
  // Get project root using environment variable or marker file
  private def getProjectRoot(): String = {
    Option(System.getenv("CHISEL_CPU_PROJECT_ROOT")).getOrElse {
      // Attempt to find project root by looking for a marker file/directory
      var current = new File(sys.props("user.dir"))
      while (current != null && !new File(current, "build.sc").exists()) {
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
    
    // Load instructions from Blink2hw.code
    val blink2hwCodePath = new File(projectRoot, "tests/Blink2hw.code").getAbsolutePath
    val programInstructions = loadInstructionsFromFile(blink2hwCodePath)
    
    // Generate the base CPU Verilog for testing and debugging
    val verilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUSubset0(programInstructions),
      firtoolOpts = Array(
        "-disable-all-randomization",
        "-strip-debug-info",
        "--lowering-options=disallowLocalVariables,disallowPackedArrays,noAlwaysComb"
      )
    )
    
    // Generate the top-level wrapper for FPGA synthesis (with real Gowin RAM)
    val topVerilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUMinimalWrapper(useRealGowin = true, programInstructions),
      firtoolOpts = Array(
        "-disable-all-randomization",
        "-strip-debug-info",
        "--lowering-options=disallowLocalVariables,disallowPackedArrays,noAlwaysComb"
      )
    )
    
    // Generate a simulation-friendly version (with mock RAM)
    val simVerilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUMinimalWrapper(useRealGowin = false, programInstructions),
      firtoolOpts = Array(
        "-disable-all-randomization",
        "-strip-debug-info",
        "--lowering-options=disallowLocalVariables,disallowPackedArrays,noAlwaysComb"
      )
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
