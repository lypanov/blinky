package gcd

import chisel3._
import chisel3.util._

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
  
  // State enum as UInt values
  val s_idle = 0.U(2.W)
  val s_start = 1.U(2.W)
  val s_send_byte = 2.U(2.W)
  val s_stop = 3.U(2.W)

  // Registers
  val state = RegInit(s_idle)
  val cycle_cnt = RegInit(0.U(16.W))
  val bit_cnt = RegInit(0.U(3.W))
  val tx_data_latch = RegInit(0.U(8.W))
  val tx_reg = RegInit(true.B)
  val tx_data_ready = RegInit(false.B)

  // State Machine
  val next_state = Wire(UInt())
  next_state := state

  switch(state) {
    is(s_idle) {
      when(io.tx_data_valid) {
        next_state := s_start
      }
    }
    is(s_start) {
      when(cycle_cnt === CYCLE - 1.U) {
        next_state := s_send_byte
      }
    }
    is(s_send_byte) {
      when(cycle_cnt === CYCLE - 1.U && bit_cnt === 7.U) {
        next_state := s_stop
      }
    }
    is(s_stop) {
      when(cycle_cnt === CYCLE - 1.U) {
        next_state := s_idle
      }
    }
  }

  // Synchronous logic with reset
  when(!io.rst_n) {
    state := s_idle
    tx_data_ready := false.B
    tx_data_latch := 0.U
    bit_cnt := 0.U
    cycle_cnt := 0.U
    tx_reg := true.B
  }.otherwise {
    state := next_state

    // tx_data_ready logic
    when(state === s_idle) {
      when(io.tx_data_valid) {
        tx_data_ready := false.B
      }.otherwise {
        tx_data_ready := true.B
      }
    }.elsewhen(state === s_stop && cycle_cnt === CYCLE - 1.U) {
      tx_data_ready := true.B
    }

    // tx_data_latch logic
    when(state === s_idle && io.tx_data_valid) {
      tx_data_latch := io.tx_data
    }

    // bit_cnt logic
    when(state === s_send_byte && cycle_cnt === CYCLE - 1.U) {
      bit_cnt := bit_cnt + 1.U
    }.elsewhen(state =/= s_send_byte) {
      bit_cnt := 0.U
    }

    // cycle_cnt logic
    when((state === s_send_byte && cycle_cnt === CYCLE - 1.U) || next_state =/= state) {
      cycle_cnt := 0.U
    }.otherwise {
      cycle_cnt := cycle_cnt + 1.U
    }

    // tx_reg logic
    switch(state) {
      is(s_idle) { tx_reg := true.B }
      is(s_stop) { tx_reg := true.B }
      is(s_start) { tx_reg := false.B }
      is(s_send_byte) { tx_reg := tx_data_latch(bit_cnt) }
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
  val HALF_CYCLE = (CLK_FRE * 500000 / BAUD_RATE).U  // Half of CYCLE, calculated directly
  
  // State enum as UInt values with rx_ prefix to avoid name conflicts
  val rx_idle = 0.U(3.W)
  val rx_start = 1.U(3.W)
  val rx_rec_byte = 2.U(3.W)
  val rx_stop = 3.U(3.W)
  val rx_data = 4.U(3.W)

  // Registers
  val state = RegInit(rx_idle)
  val rx_d0 = RegInit(false.B)
  val rx_d1 = RegInit(false.B)
  val rx_bits = RegInit(0.U(8.W))
  val cycle_cnt = RegInit(0.U(16.W))
  val bit_cnt = RegInit(0.U(3.W))
  val rx_data_reg = RegInit(0.U(8.W))
  val rx_data_valid_reg = RegInit(false.B)

  // Edge detection
  val rx_negedge = rx_d1 && !rx_d0

  // State Machine
  val next_state = Wire(UInt())
  next_state := state

  switch(state) {
    is(rx_idle) {
      when(rx_negedge) { next_state := rx_start }
    }
    is(rx_start) {
      when(cycle_cnt === CYCLE - 1.U) { next_state := rx_rec_byte }
    }
    is(rx_rec_byte) {
      when(cycle_cnt === CYCLE - 1.U && bit_cnt === 7.U) { next_state := rx_stop }
    }
    is(rx_stop) {
      when(cycle_cnt === (HALF_CYCLE - 1.U)) { next_state := rx_data }
    }
    is(rx_data) {
      when(io.rx_data_ready) { next_state := rx_idle }
    }
  }

  // Synchronous logic
  when(!io.rst_n) {
    rx_d0 := false.B
    rx_d1 := false.B
    state := rx_idle
    rx_data_valid_reg := false.B
    rx_data_reg := 0.U
    bit_cnt := 0.U
    cycle_cnt := 0.U
    rx_bits := 0.U
  }.otherwise {
    rx_d0 := io.rx_pin
    rx_d1 := rx_d0
    state := next_state

    // rx_data_valid logic
    when(state === rx_stop && next_state =/= state) {
      rx_data_valid_reg := true.B
    }.elsewhen(state === rx_data && io.rx_data_ready) {
      rx_data_valid_reg := false.B
    }

    // rx_data logic
    when(state === rx_stop && next_state =/= state) {
      rx_data_reg := rx_bits
    }

    // bit_cnt logic
    when(state === rx_rec_byte && cycle_cnt === CYCLE - 1.U) {
      bit_cnt := bit_cnt + 1.U
    }.elsewhen(state =/= rx_rec_byte) {
      bit_cnt := 0.U
    }

    // cycle_cnt logic
    when((state === rx_rec_byte && cycle_cnt === CYCLE - 1.U) || next_state =/= state) {
      cycle_cnt := 0.U
    }.otherwise {
      cycle_cnt := cycle_cnt + 1.U
    }

    // rx_bits logic - fix the bit assignment
    when(state === rx_rec_byte && cycle_cnt === (HALF_CYCLE - 1.U)) {
      // Create a new value for rx_bits by setting a specific bit
      val new_rx_bits = rx_bits
      when(io.rx_pin) {
        rx_bits := new_rx_bits | (1.U(8.W) << bit_cnt)
      }.otherwise {
        rx_bits := new_rx_bits & ~(1.U(8.W) << bit_cnt)
      }
    }
  }

  io.rx_data := rx_data_reg
  io.rx_data_valid := rx_data_valid_reg
}