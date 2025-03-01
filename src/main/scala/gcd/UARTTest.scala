package gcd

import chisel3._
import chisel3.util._

// UART Transmitter Module
class UartTx(val CLK_FRE: Int = 50, val BAUD_RATE: Int = 115200) extends Module {
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val rst_n = Input(Bool())
    val tx_data = Input(UInt(8.W))
    val tx_data_valid = Input(Bool())
    val tx_data_ready = Output(Bool())
    val tx_pin = Output(Bool())
  })

  // Parameters and Constants
  val CYCLE = (CLK_FRE * 1000000 / BAUD_RATE).U
  val S_IDLE :: S_START :: S_SEND_BYTE :: S_STOP :: Nil = Enum(4)

  // Registers
  val state = RegInit(S_IDLE)
  val cycle_cnt = RegInit(0.U(16.W))
  val bit_cnt = RegInit(0.U(3.W))
  val tx_data_latch = RegInit(0.U(8.W))
  val tx_reg = RegInit(true.B)
  val tx_data_ready = RegInit(false.B)

  // State Machine
  val next_state = Wire(UInt())
  next_state := state

  switch(state) {
    is(S_IDLE) {
      when(io.tx_data_valid) {
        next_state := S_START
      }
    }
    is(S_START) {
      when(cycle_cnt === CYCLE - 1.U) {
        next_state := S_SEND_BYTE
      }
    }
    is(S_SEND_BYTE) {
      when(cycle_cnt === CYCLE - 1.U && bit_cnt === 7.U) {
        next_state := S_STOP
      }
    }
    is(S_STOP) {
      when(cycle_cnt === CYCLE - 1.U) {
        next_state := S_IDLE
      }
    }
  }

  // Synchronous logic with reset
  when(!io.rst_n) {
    state := S_IDLE
    tx_data_ready := false.B
    tx_data_latch := 0.U
    bit_cnt := 0.U
    cycle_cnt := 0.U
    tx_reg := true.B
  }.otherwise {
    state := next_state

    // tx_data_ready logic
    when(state === S_IDLE) {
      when(io.tx_data_valid) {
        tx_data_ready := false.B
      }.otherwise {
        tx_data_ready := true.B
      }
    }.elsewhen(state === S_STOP && cycle_cnt === CYCLE - 1.U) {
      tx_data_ready := true.B
    }

    // tx_data_latch logic
    when(state === S_IDLE && io.tx_data_valid) {
      tx_data_latch := io.tx_data
    }

    // bit_cnt logic
    when(state === S_SEND_BYTE && cycle_cnt === CYCLE - 1.U) {
      bit_cnt := bit_cnt + 1.U
    }.elsewhen(state =/= S_SEND_BYTE) {
      bit_cnt := 0.U
    }

    // cycle_cnt logic
    when((state === S_SEND_BYTE && cycle_cnt === CYCLE - 1.U) || next_state =/= state) {
      cycle_cnt := 0.U
    }.otherwise {
      cycle_cnt := cycle_cnt + 1.U
    }

    // tx_reg logic
    switch(state) {
      is(S_IDLE) { tx_reg := true.B }
      is(S_STOP) { tx_reg := true.B }
      is(S_START) { tx_reg := false.B }
      is(S_SEND_BYTE) { tx_reg := tx_data_latch(bit_cnt) }
    }
  }

  // Outputs
  io.tx_data_ready := tx_data_ready
  io.tx_pin := tx_reg
}

// UART Receiver Module
class UartRx(val CLK_FRE: Int = 50, val BAUD_RATE: Int = 115200) extends Module {
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val rst_n = Input(Bool())
    val rx_data = Output(UInt(8.W))
    val rx_data_valid = Output(Bool())
    val rx_data_ready = Input(Bool())
    val rx_pin = Input(Bool())
  })

  val CYCLE = (CLK_FRE * 1000000 / BAUD_RATE).U
  val S_IDLE :: S_START :: S_REC_BYTE :: S_STOP :: S_DATA :: Nil = Enum(5)

  // Registers
  val state = RegInit(S_IDLE)
  val rx_d0 = RegInit(false.B)
  val rx_d1 = RegInit(false.B)
  val rx_bits = RegInit(0.U(8.W))
  val cycle_cnt = RegInit(0.U(16.W))
  val bit_cnt = RegInit(0.U(3.W))
  val rx_data = RegInit(0.U(8.W))
  val rx_data_valid = RegInit(false.B)

  // Edge detection
  val rx_negedge = rx_d1 && !rx_d0

  // State Machine
  val next_state = Wire(UInt())
  next_state := state

  switch(state) {
    is(S_IDLE) {
      when(rx_negedge) { next_state := S_START }
    }
    is(S_START) {
      when(cycle_cnt === CYCLE - 1.U) { next_state := S_REC_BYTE }
    }
    is(S_REC_BYTE) {
      when(cycle_cnt === CYCLE - 1.U && bit_cnt === 7.U) { next_state := S_STOP }
    }
    is(S_STOP) {
      when(cycle_cnt === (CYCLE/2 - 1.U)) { next_state := S_DATA }
    }
    is(S_DATA) {
      when(io.rx_data_ready) { next_state := S_IDLE }
    }
  }

  // Synchronous logic
  when(!io.rst_n) {
    rx_d0 := false.B
    rx_d1 := false.B
    state := S_IDLE
    rx_data_valid := false.B
    rx_data := 0.U
    bit_cnt := 0.U
    cycle_cnt := 0.U
    rx_bits := 0.U
  }.otherwise {
    rx_d0 := io.rx_pin
    rx_d1 := rx_d0
    state := next_state

    // rx_data_valid logic
    when(state === S_STOP && next_state =/= state) {
      rx_data_valid := true.B
    }.elsewhen(state === S_DATA && io.rx_data_ready) {
      rx_data_valid := false.B
    }

    // rx_data logic
    when(state === S_STOP && next_state =/= state) {
      rx_data := rx_bits
    }

    // bit_cnt logic
    when(state === S_REC_BYTE && cycle_cnt === CYCLE - 1.U) {
      bit_cnt := bit_cnt + 1.U
    }.elsewhen(state =/= S_REC_BYTE) {
      bit_cnt := 0.U
    }

    // cycle_cnt logic
    when((state === S_REC_BYTE && cycle_cnt === CYCLE - 1.U) || next_state =/= state) {
      cycle_cnt := 0.U
    }.otherwise {
      cycle_cnt := cycle_cnt + 1.U
    }

    // rx_bits logic
    when(state === S_REC_BYTE && cycle_cnt === (CYCLE/2 - 1.U)) {
      rx_bits(bit_cnt) := io.rx_pin
    }
  }

  io.rx_data := rx_data
  io.rx_data_valid := rx_data_valid
}

// UART Test Module
class UartTest extends Module {
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val rst_n = Input(Bool())
    val uart_rx = Input(Bool())
    val uart_tx = Output(Bool())
  })

  val CLK_FRE = 27
  val UART_FRE = 115200
  val IDLE :: SEND :: WAIT :: Nil = Enum(3)
  val ENG_NUM = 9
  val CHE_NUM = 3
  val DATA_NUM = CHE_NUM * 2 + ENG_NUM

  // Registers
  val tx_data = RegInit(0.U(8.W))
  val tx_data_valid = RegInit(false.B)
  val tx_cnt = RegInit(0.U(8.W))
  val wait_cnt = RegInit(0.U(32.W))
  val state = RegInit(IDLE)

  // UART instances
  val uartRx = Module(new UartRx(CLK_FRE, UART_FRE))
  val uartTx = Module(new UartTx(CLK_FRE, UART_FRE))

  // Connections
  uartRx.io.clk := io.clk
  uartRx.io.rst_n := io.rst_n
  uartRx.io.rx_pin := io.uart_rx
  uartRx.io.rx_data_ready := true.B

  uartTx.io.clk := io.clk
  uartTx.io.rst_n := io.rst_n
  uartTx.io.tx_data := tx_data
  uartTx.io.tx_data_valid := tx_data_valid
  io.uart_tx := uartTx.io.tx_pin

  // Send data
  val send_data = "你好  GOWIN".getBytes("UTF-8") ++ Array[Byte](0x0d, 0x0a)
  val tx_str = VecInit(send_data.map(_.U(8.W)))
  
  // State Machine
  when(!io.rst_n) {
    wait_cnt := 0.U
    tx_data := 0.U
    state := IDLE
    tx_cnt := 0.U
    tx_data_valid := false.B
  }.otherwise {
    switch(state) {
      is(IDLE) {
        state := SEND
      }
      is(SEND) {
        wait_cnt := 0.U
        tx_data := tx_str(DATA_NUM.U - 1.U - tx_cnt)

        when(tx_data_valid && uartTx.io.tx_data_ready && tx_cnt < (DATA_NUM - 1).U) {
          tx_cnt := tx_cnt + 1.U
        }.elsewhen(tx_data_valid && uartTx.io.tx_data_ready) {
          tx_cnt := 0.U
          tx_data_valid := false.B
          state := WAIT
        }.elsewhen(!tx_data_valid) {
          tx_data_valid := true.B
        }
      }
      is(WAIT) {
        wait_cnt := wait_cnt + 1.U

        when(uartRx.io.rx_data_valid) {
          tx_data_valid := true.B
          tx_data := uartRx.io.rx_data
        }.elsewhen(tx_data_valid && uartTx.io.tx_data_ready) {
          tx_data_valid := false.B
        }.elsewhen(wait_cnt >= (CLK_FRE * 1000000).U) {
          state := SEND
        }
      }
    }
  }
}

// // Object to generate Verilog
// object UartTest extends App {
//   (new chisel3.stage.ChiselStage).emitVerilog(new UartTest())
// }
