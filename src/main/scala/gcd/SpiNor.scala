package gcd

import chisel3._
import chisel3.util._

// One 03h read of a little-endian word. Mode 0, MSB first. CS frames the
// command, the 24-bit address, and the four data bytes, then rises.
// `half` is the SCLK high time and the SCLK low time, in clock cycles.
// The shift matches gowin/spi_flash_pathfinder.v, which the disk model
// and the Nano NOR both accepted.
class SpiNor(half: Int = 4) extends Module {
  val io = IO(new Bundle {
    val start = Input(Bool())
    val addr = Input(UInt(24.W))
    val word = Output(UInt(32.W))
    val busy = Output(Bool())
    val done = Output(Bool())
    val csN = Output(Bool())
    val sclk = Output(Bool())
    val mosi = Output(Bool())
    val miso = Input(Bool())
  })
  require(half >= 1)

  val idle :: setup :: kick :: wait_ :: Nil = Enum(4)
  val state = RegInit(idle)
  val csN = RegInit(true.B)
  val addrReg = Reg(UInt(24.W))
  val setupN = Reg(UInt(3.W))
  val pos = Reg(UInt(4.W))
  val b0 = Reg(UInt(8.W))
  val b1 = Reg(UInt(8.W))
  val b2 = Reg(UInt(8.W))
  val word = Reg(UInt(32.W))
  val done = RegInit(false.B)

  val shiftStart = WireDefault(false.B)
  val tx = Wire(UInt(8.W))
  tx := 0.U
  when (pos === 0.U) {
    tx := 0x03.U
  } .elsewhen (pos === 1.U) {
    tx := addrReg(23, 16)
  } .elsewhen (pos === 2.U) {
    tx := addrReg(15, 8)
  } .elsewhen (pos === 3.U) {
    tx := addrReg(7, 0)
  }

  val shift = Module(new SpiShift(half))
  shift.io.start := shiftStart
  shift.io.tx := tx
  shift.io.miso := io.miso

  done := false.B
  shiftStart := false.B
  switch (state) {
    is (idle) {
      csN := true.B
      when (io.start) {
        addrReg := io.addr
        csN := false.B
        setupN := 4.U
        pos := 0.U
        state := setup
      }
    }
    is (setup) {
      csN := false.B
      when (setupN === 0.U) {
        state := kick
      } .otherwise {
        setupN := setupN - 1.U
      }
    }
    is (kick) {
      csN := false.B
      shiftStart := true.B
      state := wait_
    }
    is (wait_) {
      csN := false.B
      when (shift.io.done) {
        when (pos === 4.U) {
          b0 := shift.io.rx
        } .elsewhen (pos === 5.U) {
          b1 := shift.io.rx
        } .elsewhen (pos === 6.U) {
          b2 := shift.io.rx
        }
        when (pos === 7.U) {
          word := Cat(shift.io.rx, b2, b1, b0)
          done := true.B
          csN := true.B
          state := idle
        } .otherwise {
          pos := pos + 1.U
          state := kick
        }
      }
    }
  }

  io.csN := csN
  io.sclk := shift.io.sclk
  io.mosi := shift.io.mosi
  io.word := word
  io.done := done
  io.busy := state =/= idle
}

// One byte. SCLK rises in the low half and falls in the high half.
// MISO is sampled on the rising edge, which is the same edge the NOR model
// uses. HALF is at least 1.
class SpiShift(half: Int) extends Module {
  val io = IO(new Bundle {
    val start = Input(Bool())
    val tx = Input(UInt(8.W))
    val rx = Output(UInt(8.W))
    val done = Output(Bool())
    val sclk = Output(Bool())
    val mosi = Output(Bool())
    val miso = Input(Bool())
  })

  val running = RegInit(false.B)
  val hi = RegInit(false.B)
  val div = RegInit(0.U(16.W))
  val bitn = RegInit(0.U(3.W))
  val txsh = RegInit(0.U(8.W))
  val rxsh = RegInit(0.U(8.W))
  val rx = RegInit(0.U(8.W))
  val sclk = RegInit(false.B)
  val mosi = RegInit(false.B)
  val done = RegInit(false.B)
  val halfM1 = (half - 1).U(16.W)

  done := false.B
  when (io.start && !running) {
    running := true.B
    hi := false.B
    div := 0.U
    bitn := 0.U
    txsh := Cat(io.tx(6, 0), 0.U(1.W))
    rxsh := 0.U
    sclk := false.B
    mosi := io.tx(7)
  } .elsewhen (running) {
    when (div =/= halfM1) {
      div := div + 1.U
    } .otherwise {
      div := 0.U
      when (!hi) {
        sclk := true.B
        hi := true.B
        rxsh := Cat(rxsh(6, 0), io.miso)
      } .otherwise {
        sclk := false.B
        hi := false.B
        when (bitn === 7.U) {
          running := false.B
          done := true.B
          rx := rxsh
        } .otherwise {
          bitn := bitn + 1.U
          mosi := txsh(7)
          txsh := Cat(txsh(6, 0), 0.U(1.W))
        }
      }
    }
  }

  io.rx := rx
  io.done := done
  io.sclk := sclk
  io.mosi := mosi
}
