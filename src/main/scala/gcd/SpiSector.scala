package gcd

import chisel3._
import chisel3.util._
import java.io.{File, PrintWriter}

// Sector bytes for Kernel.ReadSD. A synchronous read maps to BSRAM.
// The hex is the three pages sim/sector_image.py builds. Firtool does not
// emit this file; the elaborator writes it next to InstrRom.
class SectorRom(hexPath: String) extends BlackBox {
  override def desiredName = "SectorRom"
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val addr = Input(UInt(10.W))
    val data = Output(UInt(32.W))
  })
  private val romFile = new File("generated/SectorRom.v")
  romFile.getParentFile.mkdirs()
  val romWriter = new PrintWriter(romFile)
  romWriter.write(
    s"""module SectorRom(
       |  input clk,
       |  input [9:0] addr,
       |  output reg [31:0] data
       |);
       |  reg [31:0] mem [0:1023];
       |  initial $$readmemh("${hexPath}", mem);
       |  always @(posedge clk) begin
       |    data <= mem[addr];
       |  end
       |endmodule
       |""".stripMargin)
  romWriter.close()
}

// SPI data at -48 and control at -44. There is no card and no pin.
// A data write clocks one byte, or one little-endian word when the fast
// bit is set during the ReadSD payload. Ready is bit 0 of the control
// read. It drops on a fast word and is set again with the word, which
// is what the poll in Kernel.SPI waits for.
// pairCount > 0 reads a packed (index, word) table through romAddr/romData
// instead of a flat sector ROM. The table is the live words of the three
// pages. A missing index returns 0. Ready stays low for the scan, which is
// what Kernel.SPI polls.
class SpiSector(pairCount: Int = 0) extends Module {
  val io = IO(new Bundle {
    val write = Input(Bool())
    val ctrl = Input(Bool())
    val wdata = Input(UInt(32.W))
    val ready = Output(Bool())
    val rdata = Output(UInt(32.W))
    val cdata = Output(UInt(32.W))
    val romAddr = Output(UInt(12.W))
    val romData = Input(UInt(32.W))
    val scanning = Output(Bool())
  })
  io.romAddr := 0.U

  val internal = if (pairCount == 0) {
    val root = sys.env.getOrElse("CHISEL_CPU_PROJECT_ROOT", new File(".").getAbsolutePath)
    val hex = new File(root, "sim/visualizer/imem/sector.hex")
    if (!hex.isFile) {
      throw new RuntimeException(s"sector ROM missing at ${hex.getAbsolutePath}")
    }
    val rom = Module(new SectorRom(hex.getAbsolutePath))
    rom.io.clk := clock
    Some(rom)
  } else None

  val ctrlReg = RegInit(0.U(4.W))
  val readyReg = RegInit(true.B)
  val rx = RegInit(0xff.U(32.W))
  val phase = RegInit(0.U(3.W))
  val cmd = RegInit(0.U(6.W))
  val arg = RegInit(0.U(32.W))
  val nargs = RegInit(0.U(3.W))
  val idx = RegInit(0.U(8.W))
  val block = RegInit(0.U(32.W))
  val wordWait = RegInit(false.B)

  val isFs = block(31, 16) === 0x0008.U
  val rel = block(15, 0)
  val half = rel(0)
  val index = rel(15, 1)
  val inRange = isFs && index >= 1.U && index <= 3.U
  val which = index - 1.U
  val wordAddr = Cat(which(1, 0), half, idx(6, 0))
  internal.foreach { rom =>
    rom.io.addr := Mux(inRange, wordAddr, 0.U)
  }
  val scan = if (pairCount > 0) RegInit(false.B) else false.B
  val scanAt = if (pairCount > 0) RegInit(0.U(8.W)) else 0.U
  val scanPhase = if (pairCount > 0) RegInit(0.U(2.W)) else 0.U
  val scanKey = if (pairCount > 0) Reg(UInt(10.W)) else 0.U(10.W)
  if (pairCount > 0) {
    when (scan) {
      when (scanPhase === 0.U) {
        io.romAddr := scanAt << 1
        scanPhase := 1.U
      } .elsewhen (scanPhase === 1.U) {
        scanKey := io.romData(9, 0)
        io.romAddr := (scanAt << 1) + 1.U
        scanPhase := 2.U
      }
    }
  }

  val byte = io.wdata(7, 0)
  val ocr = MuxLookup(idx(2, 0), 0.U(8.W))(Seq(
    0.U -> 0x00.U(8.W),
    1.U -> 0xc0.U(8.W),
    2.U -> 0xff.U(8.W),
    3.U -> 0x80.U(8.W),
    4.U -> 0x00.U(8.W)
  ))

  when (io.write && io.ctrl) {
    ctrlReg := io.wdata(3, 0)
  }

  def deliver(word: UInt): Unit = {
    rx := word
    readyReg := true.B
    wordWait := false.B
    when (idx === 127.U) {
      phase := 5.U
      idx := 0.U
    } .otherwise {
      idx := idx + 1.U
    }
  }

  def acceptByte(): Unit = {
    when (phase === 4.U && ctrlReg(2)) {
      readyReg := false.B
      if (pairCount > 0) {
        scan := true.B
        scanAt := 0.U
        scanPhase := 0.U
      } else {
        wordWait := true.B
      }
    } .otherwise {
      readyReg := true.B
      when (phase === 0.U) {
        rx := 0xff.U
        when (byte >= 0x40.U && byte <= 0x7f.U) {
          cmd := byte(5, 0)
          arg := 0.U
          nargs := 0.U
          phase := 1.U
        }
      } .elsewhen (phase === 1.U) {
        rx := 0xff.U
        when (nargs < 4.U) {
          arg := Cat(arg(23, 0), byte)
          nargs := nargs + 1.U
        } .otherwise {
          block := arg
          idx := 0.U
          phase := Mux(cmd === 58.U, 2.U, Mux(cmd === 17.U, 3.U, 0.U))
        }
      } .elsewhen (phase === 2.U) {
        rx := Cat(0.U(24.W), ocr)
        when (idx === 4.U) {
          phase := 0.U
          idx := 0.U
        } .otherwise {
          idx := idx + 1.U
        }
      } .elsewhen (phase === 3.U) {
        when (idx === 0.U) {
          rx := 0.U
          idx := 1.U
        } .otherwise {
          rx := 0xfe.U
          phase := 4.U
          idx := 0.U
        }
      } .elsewhen (phase === 5.U) {
        rx := 0xff.U
        when (idx === 1.U) {
          phase := 0.U
          idx := 0.U
        } .otherwise {
          idx := 1.U
        }
      } .otherwise {
        rx := 0xff.U
      }
    }
  }

  if (pairCount == 0) {
    when (wordWait) {
      deliver(Mux(inRange, internal.get.io.data, 0.U))
    } .elsewhen (io.write && !io.ctrl) {
      acceptByte()
    }
  } else {
    when (scan && scanPhase === 2.U) {
      val hit = scanKey === wordAddr
      val last = scanAt === (pairCount - 1).U(8.W)
      when (hit || last || !inRange) {
        deliver(Mux(hit && inRange, io.romData, 0.U))
        scan := false.B
      } .otherwise {
        scanAt := scanAt + 1.U
        scanPhase := 0.U
      }
    } .elsewhen (io.write && !io.ctrl && !scan) {
      acceptByte()
    }
  }

  io.ready := readyReg
  io.rdata := rx
  io.cdata := Cat(0.U(31.W), readyReg)
  io.scanning := scan
}
