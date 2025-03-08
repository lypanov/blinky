package gcd

import chisel3._
import chisel3.util._

// Controller for CPU memory access 
class MemoryController(val useRealGowin: Boolean = true, val queueDepth: Int = 8, val clockFreq: Int = 27000000) extends Module {
  val io = IO(new Bundle {
    // CPU memory interface
    val cpuAddr = Input(UInt(32.W))
    val cpuWriteData = Input(UInt(32.W))
    val cpuWrite = Input(Bool())
    val cpuRead = Input(Bool())
    val cpuReadData = Output(UInt(32.W))
    // val logOut = Decoupled(new LogEntry)
  })

  // Map CPU address to RAM - for now we'll just use the lower 6 bits
  // which gives access to our 64 words of memory
  val ramAddr = io.cpuAddr(7, 2)  // Get word address (bits 7:2)
  
  // Create appropriate RAM module based on parameter
  val ram: RAMInterface = if (useRealGowin) Module(new GowinSP()) else Module(new MockGowinSP())
  
  // Connect RAM signals
  ram.io.clk := clock
  ram.io.ce := io.cpuRead || io.cpuWrite
  ram.io.reset := false.B
  ram.io.wre := io.cpuWrite
  ram.io.ad := ramAddr(5, 0)
  ram.io.din := io.cpuWriteData
  ram.io.oce := true.B
  
  // Connect read data back to CPU
  io.cpuReadData := ram.io.dout
  
  // Local cache for address 0x10
  val targetAddr = 0x14.U
  val cacheValue = RegInit(0.U(32.W))

  // Update cache on writes to 0x10
  when(io.cpuWrite && io.cpuAddr === targetAddr) {
    cacheValue := io.cpuWriteData
  }

  // Handle reads with one-cycle latency
  val readPending = RegInit(false.B)
  when(io.cpuRead && io.cpuAddr === targetAddr) {
    readPending := true.B
  }.elsewhen(readPending) {
    cacheValue := ram.io.dout  // Update cache with read data after latency
    readPending := false.B
  }

  // val logQueue = Module(new Queue(new LogEntry, entries = queueDepth))
  // logQueue.io.enq.valid := false.B
  // logQueue.io.enq.bits.messageCode := 0.U
  // logQueue.io.enq.bits.logByte := 0.U
  // logQueue.io.enq.bits.logByte1 := 0.U
  // io.logOut <> logQueue.io.deq
  
  // Timer for 500ms interval
  val cyclesPer500ms = (clockFreq / 2).U  // 500ms in cycles (half of a second)
  val timer = RegInit(0.U(log2Ceil((clockFreq / 2) + 1).W))
  // val dumpTrigger = timer === cyclesPer500ms - 1.U
  val dumpTrigger = false.B

  // Timer logic
  timer := timer + 1.U
  when(dumpTrigger) {
    timer := 0.U
  }
  
  // Debug output
  when (io.cpuRead) {
    printf(p"Memory Read: addr=${io.cpuAddr}, RAM addr=${ramAddr}\n")
  }
  
  when (io.cpuWrite) {
    printf(p"Memory Write: addr=${io.cpuAddr}, data=${io.cpuWriteData}, RAM addr=${ramAddr}\n")
  }
  
  // Dump cache value every 500ms
  // when(dumpTrigger && logQueue.io.enq.ready) {
  //   logQueue.io.enq.valid := true.B
  //   logQueue.io.enq.bits.messageCode := Logger.Codes.MemoryDump
  //   logQueue.io.enq.bits.logByte := cacheValue(7, 0)  // Log lower 8 bits
  // }
}