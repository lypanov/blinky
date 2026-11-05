package gcd

import chisel3._
import chisel3.util._

/**
 * pclk/4 for the CPU. The DDR3 command port stays on pclk: the controller's
 * busy and data_ready timing is in that clock, and a one-pclk crossing
 * does not close. CLKDIV is edge-aligned with pclk. The bridge samples a
 * registered CPU request on the following pclk. Stall rises then, and the
 * next CPU edge is three pclk later.
 */
class GowinClkDiv extends BlackBox {
  override def desiredName = "GowinClkDiv"
  val io = IO(new Bundle {
    val HCLKIN = Input(Clock())
    val RESETN = Input(Bool())
    val CALIB = Input(Bool())
    val CLKOUT = Output(Clock())
  })
}

/**
 * The store data and the request are a combinational path out of the
 * instruction ROM. That path does not fit in one pclk. Register it on
 * cpu_clk so the bridge samples a flop, one pclk later, which is the
 * same edge the untimed simulation already used.
 */
class Ddr3CpuPortSync extends Module {
  val io = IO(new Bundle {
    val inAddr = Input(UInt(32.W))
    val inWriteData = Input(UInt(32.W))
    val inWrite = Input(Bool())
    val inRead = Input(Bool())
    val inByte = Input(Bool())
    val addr = Output(UInt(32.W))
    val writeData = Output(UInt(32.W))
    val write = Output(Bool())
    val read = Output(Bool())
    val byte = Output(Bool())
  })
  io.addr := RegNext(io.inAddr, 0.U)
  io.writeData := RegNext(io.inWriteData, 0.U)
  io.write := RegNext(io.inWrite, false.B)
  io.read := RegNext(io.inRead, false.B)
  io.byte := RegNext(io.inByte, false.B)
}

/**
 * The request is registered on cpu_clk, so the bridge does not see it
 * until the cycle where the CPU samples stall. Without this, that sample
 * still reads low, the load completes as zero, and the pin stays dark.
 * Stall stays high from the issue cycle until the bridge has raised it
 * and dropped it again. The word is held in the bridge across that drop.
 */
class Ddr3StallAlign extends Module {
  val io = IO(new Bundle {
    val req = Input(Bool())
    val bridgeStall = Input(Bool())
    val stall = Output(Bool())
  })
  val busy = RegInit(false.B)
  val seenHigh = RegInit(false.B)
  val doneNow = busy && seenHigh && !io.bridgeStall
  io.stall := (io.req || busy) && !doneNow
  when (io.req) {
    busy := true.B
    seenHigh := false.B
  } .elsewhen (doneNow) {
    busy := false.B
    seenHigh := false.B
  } .elsewhen (busy && io.bridgeStall) {
    seenHigh := true.B
  }
}

/** Same divide, for Verilator. See sim/CpuClock.v. */
class CpuClock extends BlackBox {
  override def desiredName = "CpuClock"
  val io = IO(new Bundle {
    val clk_in = Input(Clock())
    val clk_out = Output(Clock())
  })
}

/**
 * Command port of the Dock DDR3 controller (one 16-bit word per pulse).
 *
 * rd, wr, and refresh are one-cycle pulses issued only while busy is low
 * and calib is high. A read returns dout on the data_ready pulse. The
 * controller's busy then falls. Refresh is the user's job: DDR3 will
 * forget a row that is not refreshed, and the delay loop holds `light`
 * for a whole edge.
 */
class Ddr3UserBundle extends Bundle {
  val rd = Output(Bool())
  val wr = Output(Bool())
  val refresh = Output(Bool())
  val addr = Output(UInt(26.W))
  val din = Output(UInt(16.W))
  val dout = Input(UInt(16.W))
  val data_ready = Input(Bool())
  val busy = Input(Bool())
  val calib = Input(Bool())
}

/**
 * One CPU access on the 16-bit DDR3 port.
 *
 * A word is two consecutive 16-bit words, low half first. A byte load
 * reads the half that contains the lane and places it in that half of
 * the 32-bit result. A byte store reads that half and writes it back
 * with one byte replaced, so the other byte of the half survives.
 *
 * 96.75e6 * 7.8125e-6 = 756 controller clocks, which is tREFI for this
 * 1 Gbit part (8192 refreshes in 64 ms). A due refresh runs before the
 * next CPU command and never between the two halves of one word.
 */
class Ddr3Bridge extends Module {
  val io = IO(new Bundle {
    val cpuAddr = Input(UInt(32.W))
    val cpuWriteData = Input(UInt(32.W))
    val cpuWrite = Input(Bool())
    val cpuRead = Input(Bool())
    val cpuByte = Input(Bool())
    val cpuReadData = Output(UInt(32.W))
    val memStall = Output(Bool())
    val ddr = new Ddr3UserBundle
  })

  val sIdle :: sCal :: sRef :: sRefWait :: sCmd :: sWait :: sDone :: Nil = Enum(7)
  val state = RegInit(sIdle)

  val pend = RegInit(false.B)
  val isWrite = RegInit(false.B)
  val isByte = RegInit(false.B)
  val phase = RegInit(0.U(1.W))
  val baseAddr = Reg(UInt(32.W))
  val wdata = Reg(UInt(32.W))
  val lo = RegInit(0.U(16.W))
  val hi = RegInit(0.U(16.W))
  val hold = Reg(UInt(16.W))
  val got = RegInit(false.B)
  val sawBusy = RegInit(false.B)
  // 756 clocks is one tREFI at the 96.75 MHz controller clock.
  val refCnt = RegInit(756.U(10.W))
  val doneCnt = RegInit(0.U(3.W))

  val refreshDue = refCnt === 0.U
  val lane = baseAddr(1, 0)
  val aligned = baseAddr & ~3.U(32.W)
  val cmdAddr = Mux(isByte, baseAddr(26, 1), aligned(26, 1) + phase)
  val writePhase = isWrite && (!isByte || phase === 1.U)
  val storedByte = MuxLookup(lane, wdata(7, 0))(Seq(
    0.U -> wdata(7, 0),
    1.U -> wdata(15, 8),
    2.U -> wdata(23, 16),
    3.U -> wdata(31, 24)
  ))
  val merged = Mux(lane(0), Cat(storedByte, hold(7, 0)), Cat(hold(15, 8), storedByte))
  val halfOut = Mux(isByte, merged, Mux(phase === 0.U, wdata(15, 0), wdata(31, 16)))
  val lastHalf = Mux(isByte, !isWrite || phase === 1.U, phase === 1.U)

  io.memStall := state =/= sIdle && state =/= sDone
  io.cpuReadData := Cat(hi, lo)
  io.ddr.rd := false.B
  io.ddr.wr := false.B
  io.ddr.refresh := false.B
  io.ddr.addr := cmdAddr
  io.ddr.din := halfOut

  when (state === sRefWait && sawBusy && !io.ddr.busy) {
    refCnt := 756.U
  } .elsewhen (refCnt =/= 0.U) {
    refCnt := refCnt - 1.U
  }

  def latch(): Unit = {
    baseAddr := io.cpuAddr
    wdata := io.cpuWriteData
    isWrite := io.cpuWrite
    isByte := io.cpuByte
    phase := 0.U
    lo := 0.U
    hi := 0.U
  }

  switch (state) {
    is (sIdle) {
      when (io.cpuRead || io.cpuWrite) {
        latch()
        pend := true.B
        state := Mux(!io.ddr.calib, sCal, Mux(refreshDue, sRef, sCmd))
      } .elsewhen (refreshDue && io.ddr.calib && !io.ddr.busy) {
        state := sRef
      }
    }
    is (sCal) {
      when (io.ddr.calib && !io.ddr.busy) {
        state := Mux(refreshDue, sRef, sCmd)
      }
    }
    is (sRef) {
      // The CPU pulses a load or store for one cycle and does not look at
      // memStall until the following cycle. A refresh already in progress
      // has to catch that pulse, or the CPU completes against the previous
      // word and the pattern compare fails.
      when ((io.cpuRead || io.cpuWrite) && !pend) {
        latch()
        pend := true.B
      }
      when (!io.ddr.busy) {
        io.ddr.refresh := true.B
        sawBusy := false.B
        state := sRefWait
      }
    }
    is (sRefWait) {
      val catchReq = (io.cpuRead || io.cpuWrite) && !pend
      when (catchReq) {
        latch()
        pend := true.B
      }
      when (io.ddr.busy) {
        sawBusy := true.B
      }
      when (sawBusy && !io.ddr.busy) {
        sawBusy := false.B
        // catchReq is this cycle's pulse. pend has not updated yet.
        state := Mux(pend || catchReq, sCmd, sIdle)
      }
    }
    is (sCmd) {
      when (io.ddr.calib && !io.ddr.busy) {
        io.ddr.rd := !writePhase
        io.ddr.wr := writePhase
        got := false.B
        sawBusy := false.B
        state := sWait
      }
    }
    is (sWait) {
      when (io.ddr.busy) {
        sawBusy := true.B
      }
      when (!writePhase && io.ddr.data_ready) {
        hold := io.ddr.dout
        got := true.B
        when (isByte) {
          when (lane(1)) {
            hi := io.ddr.dout
            lo := 0.U
          } .otherwise {
            lo := io.ddr.dout
            hi := 0.U
          }
        } .elsewhen (phase === 0.U) {
          lo := io.ddr.dout
        } .otherwise {
          hi := io.ddr.dout
        }
      }
      when (sawBusy && !io.ddr.busy && (writePhase || got)) {
        when (lastHalf) {
          pend := false.B
          state := sDone
        } .otherwise {
          phase := phase + 1.U
          state := sCmd
        }
      }
    }
    is (sDone) {
      // Stall is low here, and the word is held. The CPU samples every
      // four pclk and the placed path is longer than one pclk, so a
      // one-cycle low can hide in the gap and the delay loop never
      // finishes. Four cycles is one CPU period: every phase sees it.
      when (doneCnt === 3.U) {
        doneCnt := 0.U
        state := sIdle
      } .otherwise {
        doneCnt := doneCnt + 1.U
      }
    }
  }
}

/** Behavioural command port. See sim/Ddr3UserModel.v. */
class Ddr3UserModel extends BlackBox {
  override def desiredName = "Ddr3UserModel"
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val rst_n = Input(Bool())
    val rd = Input(Bool())
    val wr = Input(Bool())
    val refresh = Input(Bool())
    val addr = Input(UInt(26.W))
    val din = Input(UInt(16.W))
    val dout = Output(UInt(16.W))
    val data_ready = Output(Bool())
    val busy = Output(Bool())
    val calib = Output(Bool())
  })
}
