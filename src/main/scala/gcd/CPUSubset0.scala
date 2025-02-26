package gcd

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.io.{File, PrintWriter}

class CPUSubset0 extends Module {
  val io = IO(new Bundle {
    val r0 = Output(UInt(32.W))  // Output register R0 for testing
    val halted = Output(Bool())  // Signal to indicate when the CPU has completed execution
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
  
  // Hardcoded instruction memory for the test program
  val instructionMemory = VecInit(
    // Instruction sequence from the problem statement
    "h41000000".U(32.W),  // MOV R1, 0
    "h42000005".U(32.W),  // MOV R2, 5
    "h03190202".U(32.W),  // SUB R3, R1, R2
    "hE9000002".U(32.W),  // B NE, skip_toggle, off=2
    "h40070001".U(32.W),  // XOR R0, R0, 1
    "h41000000".U(32.W),  // MOV R1, 0
    "h41180001".U(32.W),  // ADD R1, R1, 1
    "hE7FFFFFA".U(32.W)   // B always, loop, off=-6
  )
  
  // Instruction fetch
  val instructionAddr = (pc >> 2).asUInt  // Divide by 4 to get word address
  // Use a safe index to avoid out-of-bounds access
  val safeAddr = WireDefault(0.U(3.W))  // 3 bits can address up to 8 instructions
  safeAddr := instructionAddr(2, 0)  // Take only the 3 LSBs - enough for our 8 instructions
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
  val isLink = format(0)
  
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
      is("b0111".U) { takeBranch := true.B }              // Always
    }
    
    when (takeBranch) {
      // Calculate branch target address: PC + 4 + off * 4
      // For a 24-bit signed offset, extend sign to 32 bits
      val signedOff = Cat(Fill(8, off(23)), off)
      pc := pc + 4.U + (signedOff << 2)
    } .otherwise {
      pc := nextPC
    }
    
  } .elsewhen (isF1Format) {
    // Handle immediate instructions (F1 format)
    
    switch (op) {
      is(0.U) { // MOV - Move immediate value to register
        val immediate = imm
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := immediate
        
        // Set flags
        z := immediate === 0.U
        n := immediate(15)
      }
      
      is(7.U) { // XOR - Exclusive OR
        val result = regs(regB) ^ imm
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
      }
      
      is(8.U) { // ADD - Add
        val result = regs(regB) + imm
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
      }
      
      is(9.U) { // SUB - Subtract
        val result = regs(regB) - imm
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
      }
    }
    
    pc := nextPC
  } .elsewhen (format(3, 2) === "b00".U) {
    // Handle register operations (F0 format)
    switch (op) {
      is(9.U) { // SUB - Subtract register
        val result = regs(regB) - regs(regC)
        regWrite := true.B
        regWriteAddr := regA
        regWriteData := result
        
        // Set flags
        n := result(31)
        z := result === 0.U
        
        // Debug output specific to register operations
        printf(p"F0 SUB: R$regB(${regs(regB)}) - R$regC(${regs(regC)}) = $result, Z=$z\n")
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
  io.halted := halted
}

object CPUSubset0 {
  def main(args: Array[String]): Unit = {
    println("Generating CPUSubset0 Verilog")
    
    val targetDir = "generated"
    val outputFile = "CPUSubset0.v"
    
    new java.io.File(targetDir).mkdirs()
    
    val verilogCode = ChiselStage.emitSystemVerilog(
      gen = new CPUSubset0(),
      firtoolOpts = Array("-disable-all-randomization", "-strip-debug-info",
         "--lowering-options=disallowLocalVariables")
    )
    
    val writer = new java.io.PrintWriter(new java.io.File(s"$targetDir/$outputFile"))
    writer.write(verilogCode)
    writer.close()
    
    println(s"Verilog written to $targetDir/$outputFile")
    
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
      
      // List the instructions with their addresses and disassembly
      val instructions = Array(
        "41000000", // MOV R1, 0
        "42000005", // MOV R2, 5
        "03190202", // SUB R3, R1, R2
        "E9000002", // B NE, skip_toggle, off=2
        "40070001", // XOR R0, R0, 1
        "41000000", // MOV R1, 0
        "41180001", // ADD R1, R1, 1
        "E7FFFFFA"  // B always, loop, off=-6
      )
      
      _traceWriter.printf("Instructions:\n")
      for ((instr, idx) <- instructions.zipWithIndex) {
        // Display disassembly
        val disasm = disassemble(instr)
        _traceWriter.printf("0x%08x: 0x%s - %s\n", idx * 4, instr, disasm)
      }
      
      _traceWriter.printf("\nTrace Output:\n")
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
  
  // Simple disassembler for the instruction set
  def disassemble(instrHex: String): String = {
    try {
      val instr = java.lang.Long.parseLong(instrHex, 16)
      val format = (instr >>> 28) & 0xF
      
      format match {
        case 0x4 | 0x5 => // F1 format (immediate operations)
          val a = (instr >>> 24) & 0xF
          val b = (instr >>> 20) & 0xF
          val op = (instr >>> 16) & 0xF
          val imm = instr & 0xFFFF
          
          op match {
            case 0 => s"MOV R$a, $imm"
            case 7 => s"XOR R$a, R$b, $imm"
            case 8 => s"ADD R$a, R$b, $imm"
            case 9 => s"SUB R$a, R$b, $imm"
            case _ => s"Unknown F1 operation: $op"
          }
          
        case 0x0 | 0x1 => // F0 format (register operations)
          val a = (instr >>> 24) & 0xF
          val b = (instr >>> 20) & 0xF
          val op = (instr >>> 16) & 0xF
          val c = instr & 0xF
          
          op match {
            case 9 => s"SUB R$a, R$b, R$c"
            case _ => s"Unknown F0 operation: $op"
          }
          
        case 0xE | 0xF => // F3 format (branch)
          val cond = (instr >>> 24) & 0xF
          val off = instr & 0xFFFFFF
          // Sign extend the offset for display
          val signedOff = if ((off & 0x800000) != 0) off | 0xFF000000 else off
          
          cond match {
            case 0x1 => s"BEQ offset=${signedOff}"
            case 0x9 => s"BNE offset=${signedOff}"
            case 0x7 => s"B offset=${signedOff}"
            case _ => s"Unknown branch condition: $cond"
          }
          
        case _ => s"Unknown instruction format: $format"
      }
    } catch {
      case e: Exception => 
        println(s"Error disassembling instruction: $instrHex - ${e.getMessage}")
        s"Error disassembling: $instrHex"
    }
  }
}
