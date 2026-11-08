package gcd

import chisel3._
import chisel3.experimental.IntParam
import chisel3.util._

/**
 * User-side port of Gowin's HyperRAM controller (IPUG944 Table 5-1).
 * Physical O_hpram_* / IO_hpram_* pins are not here: the encrypted PHY
 * drives those, and blinky_top_hyperram wires them from the IP.
 *
 * cmd is 0 for read and 1 for write. cmd_en is a one-cycle pulse.
 * A burst of 16 bytes is four 32-bit beats. Beat 0 is driven in the
 * same cycle as cmd_en. data_mask 0 writes a byte; 0xF masks the beat.
 */
class HyperRamUserBundle extends Bundle {
  val cmd = Output(Bool())
  val cmd_en = Output(Bool())
  val addr = Output(UInt(22.W))
  val wr_data = Output(UInt(32.W))
  val data_mask = Output(UInt(4.W))
  val rd_data = Input(UInt(32.W))
  val rd_data_valid = Input(Bool())
  val init_calib = Input(Bool())
}

/**
 * One 32-bit CPU access on a 16-byte HyperRAM burst.
 *
 * The line address is the 16-byte-aligned byte address, shifted to the
 * controller's 16-bit-word address (byte >> 1). The selected beat is
 * byte[3:2]. Writes mask the other three beats so neighbours stay put.
 * Reads count rd_data_valid pulses and keep the selected beat.
 *
 * The controller's minimum gap between cmd_en pulses is 15 user clocks
 * for a 16-byte burst at or below 166 MHz (IPUG944 Table 4-2). This
 * bridge waits until that gap has elapsed and, for a read, until the
 * selected beat has been captured. It does not assume a fixed read latency.
 */
class HyperRamBridge extends Module {
  val io = IO(new Bundle {
    val cpuAddr = Input(UInt(32.W))
    val cpuWriteData = Input(UInt(32.W))
    val cpuWrite = Input(Bool())
    val cpuRead = Input(Bool())
    val cpuByte = Input(Bool())
    val cpuReadData = Output(UInt(32.W))
    val memStall = Output(Bool())
    val hr = new HyperRamUserBundle
  })

  val sIdle :: sCmd :: sBeat :: sWait :: Nil = Enum(4)
  val state = RegInit(sIdle)

  val isWrite = RegInit(false.B)
  val byteOp = RegInit(false.B)
  val lane = Reg(UInt(2.W))
  val lineAddr = Reg(UInt(22.W))
  val slot = Reg(UInt(2.W))
  val wdata = Reg(UInt(32.W))
  val rdata = RegInit(0.U(32.W))
  val got = RegInit(false.B)
  val cyc = Reg(UInt(8.W))
  val beat = Reg(UInt(2.W))
  val rdBeat = Reg(UInt(3.W))

  // Gowin folds `en ? write : isWrite` into a write-only clock enable when
  // `write` is a term of `en`, so a load never clears isWrite and never
  // captures its address. The LUT stops that proof.
  val readBit = Module(new KeepBit)
  val writeBit = Module(new KeepBit)
  readBit.io.i := io.cpuRead
  writeBit.io.i := io.cpuWrite
  val cpuRead = readBit.io.o
  val cpuWrite = writeBit.io.o

  io.memStall := state =/= sIdle
  io.cpuReadData := rdata
  io.hr.cmd := isWrite
  io.hr.cmd_en := false.B
  io.hr.addr := lineAddr
  io.hr.wr_data := 0.U
  io.hr.data_mask := 0xF.U

  def driveBeat(b: UInt): Unit = {
    // data_mask bit 0 low writes wr_data[7:0]. A word store clears all
    // four bits of the selected beat. A byte store clears one.
    val byteMask = MuxLookup(lane, "b1110".U(4.W))(Seq(
      0.U -> "b1110".U(4.W),
      1.U -> "b1101".U(4.W),
      2.U -> "b1011".U(4.W),
      3.U -> "b0111".U(4.W)
    ))
    when(isWrite && b === slot) {
      io.hr.wr_data := wdata
      io.hr.data_mask := Mux(byteOp, byteMask, 0.U)
    }
  }

  def captureRead(): Unit = {
    when(!isWrite && io.hr.rd_data_valid) {
      when(rdBeat === slot) {
        rdata := io.hr.rd_data
        got := true.B
      }
      rdBeat := rdBeat + 1.U
    }
  }

  switch(state) {
    is(sIdle) {
      when(cpuRead || cpuWrite) {
        val lineByte = io.cpuAddr & ~15.U(32.W)
        lineAddr := lineByte(22, 1)
        slot := io.cpuAddr(3, 2)
        lane := io.cpuAddr(1, 0)
        byteOp := io.cpuByte
        wdata := io.cpuWriteData
        got := false.B
        cyc := 0.U
        beat := 1.U
        rdBeat := 0.U
        state := sCmd
      }
      // isWrite is 0 on every load. Kept out of the address block: Gowin
      // synthesis folds a shared enable down to the write term and then
      // a load neither captures its address nor clears the write flag.
      when(cpuRead) {
        isWrite := false.B
      }
      when(cpuWrite) {
        isWrite := true.B
      }
    }
    is(sCmd) {
      when(io.hr.init_calib) {
        io.hr.cmd_en := true.B
        driveBeat(0.U)
        cyc := 1.U
        state := sBeat
      }
    }
    is(sBeat) {
      driveBeat(beat)
      captureRead()
      cyc := cyc + 1.U
      when(beat === 3.U) {
        state := sWait
      }.otherwise {
        beat := beat + 1.U
      }
    }
    is(sWait) {
      captureRead()
      when((cyc >= 15.U) && (isWrite || got)) {
        state := sIdle
      }.otherwise {
        cyc := cyc + 1.U
      }
    }
  }
}

/**
 * Behavioural stand-in for the encrypted controller. See sim/HyperRamUserModel.v.
 *
 * firstValid 12 is the pre-load model (read data inside the 15-clock gap).
 * firstValid 13 is the one-clock-later read fitted after the 0.500 Hz measurement.
 */
/** One LUT. Stops Gowin proving the bit is 0 on a load. See gowin/KeepBit.v. */
class KeepBit extends BlackBox {
  override def desiredName = "KeepBit"
  val io = IO(new Bundle {
    val i = Input(Bool())
    val o = Output(Bool())
  })
}

class HyperRamUserModel(firstValid: Int = 12) extends BlackBox(Map(
  "FIRST_VALID" -> IntParam(firstValid)
)) {
  override def desiredName = "HyperRamUserModel"
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val memory_clk = Input(Clock())
    val pll_lock = Input(Bool())
    val rst_n = Input(Bool())
    val wr_data = Input(UInt(32.W))
    val rd_data = Output(UInt(32.W))
    val rd_data_valid = Output(Bool())
    val addr = Input(UInt(22.W))
    val cmd = Input(Bool())
    val cmd_en = Input(Bool())
    val init_calib = Output(Bool())
    val clk_out = Output(Clock())
    val data_mask = Input(UInt(4.W))
  })
}
