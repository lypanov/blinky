package gcd

import chisel3._
import chisel3.util._
import scala.language.experimental.macros
import scala.reflect.macros.blackbox

/** A simple definition of a log message.
  * @param code the 4-bit message code that can be used in hardware
  * @param text the associated message text (will be converted to a vector of UInts)
  */
case class LogMessage(code: UInt, text: String)

object Logger {
  // Centralized list of available messages.
  val messages: Seq[LogMessage] = Seq(
    LogMessage(0.U(4.W), "led toggled"),
    LogMessage(1.U(4.W), "你好  GOWIN3")
  )

  // Extracting named constants from our messages list.
  object Codes {
    val LedToggled = messages(0).code
    val PeriodicMessage = messages(1).code
  }

  /** Helper function to convert a message string into a vector of UInt bytes.
    * It appends a carriage return and newline.
    *
    * @param str the message text
    * @return a tuple of (vector of UInt, length as an Int)
    */
  def createMessage(str: String): (Vec[UInt], UInt) = {
    val bytesWithNewline = (str.getBytes("UTF-8") ++ Array[Byte](0x0d, 0x0a))
    val vec = VecInit(bytesWithNewline.iterator.map(b => (b & 0xFF).U(8.W)).toSeq)
    val len = bytesWithNewline.length.U
    (vec, len)
  }

  /** New logging interface for users.
    *
    * This method sets the "trigger" high and assigns the provided message code to "messageCode"
    * inside the passed io Bundle.
    *
    * @param io the IO bundle containing a "trigger" and "messageCode" signal.
    * @param messageCode the log message code from Logger.Codes.
    */
  def log(io: Bundle, messageCode: UInt): Unit = {
    // Retrieve the "trigger" and "messageCode" sub-elements from the IO Bundle.
    val trigger = io.elements.get("trigger").get.asInstanceOf[Bool]
    val msgCode = io.elements.get("messageCode").get.asInstanceOf[UInt]

    trigger := true.B
    msgCode := messageCode
  }
}

class Logger extends Module {
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val rst_n = Input(Bool())
    // Instead of passing separate message code and trigger signals,
    // you might eventually consider providing a higher level interface that directly
    // enqueues a LogMessage (or its code) based on a single consolidated signal.
    val messageCode = Input(UInt(4.W))
    val trigger = Input(Bool())
    val uart_rx = Input(Bool())
    val uart_tx = Output(Bool())
  })

  val CLK_FRE = 27
  val UART_FRE = 115200

  val sIdle = 0.U(2.W)
  val sSending = 1.U(2.W)

  val uartRx = Module(new UartRx(CLK_FRE, UART_FRE))
  val uartTx = Module(new UartTx(CLK_FRE, UART_FRE))

  uartRx.io.clk := io.clk
  uartRx.io.rst_n := io.rst_n
  uartRx.io.rx_pin := io.uart_rx
  uartRx.io.rx_data_ready := true.B

  uartTx.io.clk := io.clk
  uartTx.io.rst_n := io.rst_n
  io.uart_tx := uartTx.io.tx_pin

  // FIFO for message codes. We enqueue log messages using io.trigger and messageCode.
  val messageQueue = Module(new Queue(UInt(4.W), 16))
  messageQueue.io.enq.valid := io.trigger
  messageQueue.io.enq.bits := io.messageCode
  messageQueue.io.deq.ready := false.B

  // Registers for controlling UART transmission.
  val state = RegInit(sIdle)
  val tx_data = RegInit(0.U(8.W))
  val tx_data_valid = RegInit(false.B)
  val tx_cnt = RegInit(0.U(4.W))
  val currentMessageCode = RegInit(0.U(4.W))

  // Periodic timer.
  val periodicTimer = RegInit(0.U(32.W))
  when(periodicTimer < (CLK_FRE * 1000000).U) {
    periodicTimer := periodicTimer + 1.U
  }.otherwise {
    periodicTimer := 0.U
    when(messageQueue.io.enq.ready) {
      messageQueue.io.enq.valid := true.B
      messageQueue.io.enq.bits := Logger.Codes.PeriodicMessage
    }
  }

  when(!io.rst_n) {
    state := sIdle
    tx_data := 0.U
    tx_data_valid := false.B
    tx_cnt := 0.U
    currentMessageCode := 0.U
    periodicTimer := 0.U
  }.otherwise {
    switch(state) {
      is(sIdle) {
        when(messageQueue.io.deq.valid) {
          currentMessageCode := messageQueue.io.deq.bits
          messageQueue.io.deq.ready := true.B
          state := sSending
          tx_cnt := 0.U
        }.elsewhen(uartRx.io.rx_data_valid && !tx_data_valid) {
          tx_data := uartRx.io.rx_data
          tx_data_valid := true.B
        }
      }
      is(sSending) {
        val msgVec = Wire(Vec(16, UInt(8.W)))
        val msgLen = WireDefault(0.U(5.W))
        for (i <- 0 until 16) { msgVec(i) := 0.U }
        
        val messageData = Logger.messages.map { msg =>
          val (vec, len) = Logger.createMessage(msg.text)
          (msg.code, vec, len)
        }

        messageData.foldLeft(when(false.B) {}) { case (acc, (code, vec, len)) =>
          acc.elsewhen(currentMessageCode === code) {
            for (i <- 0 until vec.length) { msgVec(i) := vec(i) }
            msgLen := len
          }
        }

        tx_data := msgVec(tx_cnt)
        when(tx_data_valid && uartTx.io.tx_data_ready) {
          when(tx_cnt < (msgLen - 1.U)) {
            tx_cnt := tx_cnt + 1.U
          }.otherwise {
            tx_cnt := 0.U
            tx_data_valid := false.B
            state := sIdle
          }
        }.otherwise {
          tx_data_valid := true.B
        }
      }
    }
  }

  uartTx.io.tx_data := tx_data
  uartTx.io.tx_data_valid := tx_data_valid
} 