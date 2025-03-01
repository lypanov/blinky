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
  })
  
  // Program counter
  val pc = RegInit(0.U(32.W))
  
  // Registers (we'll implement R0-R3 as required by the test program)
  val regs = RegInit(VecInit(Seq.fill(4)(0.U(32.W))))
  
  // Flags
  val n = RegInit(false.B)  // Negative
  val c = RegInit(false.B)  // Carry
  val v = RegInit(false.B)  // Overflow
  val z = RegInit(false.B)  // Zero
  
  // Instruction memory from provided hex strings or default to empty
  val instructionMemory = if (instructionHexStrings.nonEmpty) {
    VecInit(instructionHexStrings.map(hex => s"h$hex".U(32.W)))
  } else {
    // Default empty instruction memory
    VecInit(Seq.fill(1)(0.U(32.W)))
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
  
  // Safely access registers using only the necessary bits
  val regA = a(1, 0)  // 2 bits for 4 registers
  val regB = b(1, 0)  // 2 bits for 4 registers
  val regC = c_reg(1, 0)  // 2 bits for 4 registers
  
  // Determine if this is a branch instruction (F3 format starts with 11xx)
  val isBranch = format(3, 2) === "b11".U
  val isF1Format = format(3, 2) === "b01".U  // For immediate operations
  
  // By default, increment PC
  val nextPC = pc + 4.U
  
  // Default signal values
  val regWrite = Wire(Bool())
  val regWriteAddr = Wire(UInt(2.W))  // 2 bits for 4 registers
  val regWriteData = Wire(UInt(32.W))
  regWrite := false.B
  regWriteAddr := 0.U
  regWriteData := 0.U
  
  // Flag to track if CPU should halt (for simulation purposes)
  val halted = RegInit(false.B)
  
  // ALU for operation results
  val aluOut = Wire(UInt(32.W))
  aluOut := 0.U
  
  // Execution logic
  when (isBranch) {
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
      // Check if this is a branch to register (off == 0) or branch with offset
      when (off === 0.U) {
        // Branch to register: Use register c as the branch target
        // Make sure the low 2 bits are 0 (word-aligned)
        pc := regs(regC) & ~(3.U(32.W))
        
        // Debug output for branch to register
        printf(p"BT R$regC: Branching to address ${regs(regC) & ~(3.U(32.W))}\n")
      } .otherwise {
        // Calculate branch target address: PC + 4 + off * 4
        // For a 24-bit signed offset, extend sign to 32 bits
        val signedOff = Cat(Fill(8, off(23)), off)
        pc := pc + 4.U + (signedOff << 2)
      }
    } .otherwise {
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
      }
      
      is(7.U) { // XOR - Exclusive OR with immediate/register operand
        val result = regs(regB) ^ operand
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
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
      }
    }
    
    pc := nextPC
  } .otherwise {
    // For any other format (not implemented), just increment PC
    pc := nextPC
  }
  
  // Register write logic
  when (regWrite) {
    regs(regWriteAddr) := regWriteData
    
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
  printf(p"R0: ${regs(0)}, R1: ${regs(1)}, R2: ${regs(2)}, R3: ${regs(3)}, Z: ${z}\n")
  
  // Connect outputs
  io.r0 := regs(0)
  io.r1 := regs(1)
  io.r2 := regs(2)
  io.r3 := regs(3)
  io.halted := halted
  io.led := regs(0)(0)  // Connect the least significant bit of R0 to the LED
}

// Add this class after the CPUSubset0 class
class CPUMinimalWrapper extends Module {
  val io = IO(new Bundle {
    val led = Output(Bool())  // Only expose the LED output
  })
  
  // Internal CPU with the blink program
  val cpu = Module(new CPUSubset0(CPUSubset0.blinkProgram))
  io.led := cpu.io.led
}

object CPUSubset0 {
  // Move the blinkProgram to a place where it can be shared
  val blinkProgram = Seq(
    "40000000", // MOV R0, 1       ; light off
    "41000001", // MOV R1, 0       ; Initialize counter
    "62000040", // MHI R2, 0x0040  ; Set high part of loop count
    "42260001", // IOR R2, R2, 0x0001 ; Set low part of loop count (0x01000001 = ~16,777,216 iterations)
    "03190002", // SUB R3, R1, R2  ; Compare counter to max iterations
    "E9000002", // B NE, skip_toggle, off=2 (NOTE offset takes into account our random MHI instruction!)
    "40070001", // XOR R0, R0, 1   ; Toggle LED
    "41000000", // MOV R1, 0       ; Reset counter
    "41180001", // ADD R1, R1, 1   ; Increment counter
    "E7FFFFFA"  // B always, loop, off=-6
  )

  def main(args: Array[String]): Unit = {
    println("Generating CPUSubset0 Verilog")
    
    val targetDir = "generated"
    val outputFile = "CPUSubset0.v"
    val topOutputFile = "CPUMinimalWrapper.v"
    
    new java.io.File(targetDir).mkdirs()
    
    // Generate the base CPU Verilog for testing and debugging
    val verilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUSubset0(blinkProgram),
      firtoolOpts = Array(
        "-disable-all-randomization",
        "-strip-debug-info",
        "--lowering-options=disallowLocalVariables,disallowPackedArrays,noAlwaysComb"
      )
    )
    
    // Also generate the minimal top-level wrapper for FPGA synthesis
    val topVerilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUMinimalWrapper(),
      firtoolOpts = Array(
        "-disable-all-randomization",
        "-strip-debug-info",
        "--lowering-options=disallowLocalVariables,disallowPackedArrays,noAlwaysComb"
      )
    )
    
    // Write both Verilog files
    val writer = new java.io.PrintWriter(new java.io.File(s"$targetDir/$outputFile"))
    writer.write(verilogCode)
    writer.close()
    
    val topWriter = new java.io.PrintWriter(new java.io.File(s"$targetDir/$topOutputFile"))
    topWriter.write(topVerilogCode)
    topWriter.close()
    
    println(s"Verilog written to $targetDir/$outputFile")
    println(s"Top-level wrapper written to $targetDir/$topOutputFile")
    
    // Also create a trace directory if it doesn't exist
    val traceDir = "trace"
    new java.io.File(traceDir).mkdirs()
    println(s"Created trace directory at $traceDir")
    
    // Initialize the trace file
    CPUSubset0Companion.initializeTraceWriter()
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
  
  def initializeTraceWriter(): Unit = {
    if (_traceWriter == null) {
      val traceDir = "trace"
      new java.io.File(traceDir).mkdirs()
      val traceFileName = s"$traceDir/cpu_trace.txt"
      _traceWriter = new TeePrintWriter(traceFileName)
      
      // Write header
      _traceWriter.printf("CPU Simulation Trace\n")
      _traceWriter.printf("==================\n\n")
      
      // We no longer list instructions here - they will be output during CPU execution
      // and read by the trace analyzer
      
      _traceWriter.printf("Trace Output:\n")
      _traceWriter.printf("=============\n\n")
      
      println(s"CPU trace initialized to $traceFileName")
    }
  }
  
  def traceWriter: TeePrintWriter = {
    if (_traceWriter == null) {
      initializeTraceWriter()
    }
    _traceWriter
  }
  
  def printTrace(msg: String): Unit = {
    traceWriter.printf(msg)
  }
}
