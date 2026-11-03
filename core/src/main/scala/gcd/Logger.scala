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
    LogMessage(0.U(4.W), "led toggle: "),
    LogMessage(1.U(4.W), "GOWIN 1234567"),
  )

  // Extracting named constants from our messages list.
  object Codes {
    val LedToggle = messages(0).code  // Used for LED events (with an attached value)
    val PeriodicMessage = messages(1).code
  }

  val maxMessageLength: Int = messages.map { msg =>
    msg.text.getBytes("UTF-8").length + 2  // +2 for CR+LF
  }.max

  /** Helper function to convert a message string into a vector of UInt bytes.
    * It appends a carriage return and newline.
    *
    * @param str the message text
    * @return a tuple of (vector of UInt, length as an Int)
    */
  def createMessage(str: String): (Vec[UInt], UInt) = {
    val bytesWithNewline = (Array[Byte](0x0d, 0x0a) ++ str.getBytes("UTF-8"))
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
    * @param value the extra 8-bit value to be sent with the message
    */
  def log(io: Bundle, messageCode: UInt, value: UInt = 0.U(8.W)): Unit = {
    // Retrieve the "trigger", "messageCode", and our new "logByte" signals from the IO Bundle.
    val trigger = io.elements.get("trigger").get.asInstanceOf[Bool]
    val msgCode = io.elements.get("messageCode").get.asInstanceOf[UInt]
    val logByte = io.elements.get("logByte").get.asInstanceOf[UInt]

    trigger := true.B
    msgCode := messageCode
    logByte := value
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
    val logByte = Input(UInt(8.W))
    val uart_rx = Input(Bool())
    val uart_tx = Output(Bool())
  })

  val CLK_FRE = 27
  val UART_FRE = 115200

  val sIdle    = 0.U(2.W)
  val sSending = 1.U(2.W)
  val sAppending = 2.U(2.W)  // New state for appending the hex log byte

  val uartRx = Module(new UartRx(CLK_FRE, UART_FRE))
  val uartTx = Module(new UartTx(CLK_FRE, UART_FRE))

  uartRx.io.clk := io.clk
  uartRx.io.rst_n := io.rst_n
  uartRx.io.rx_pin := io.uart_rx
  uartRx.io.rx_data_ready := true.B

  uartTx.io.clk := io.clk
  uartTx.io.rst_n := io.rst_n
  io.uart_tx := uartTx.io.tx_pin

  // Define a Bundle for queue entries that includes both messageCode and logByte
  class LogEntry extends Bundle {
    val messageCode = UInt(4.W)
    val logByte = UInt(8.W)
  }

  // FIFO for message entries. We enqueue log messages using io.trigger, messageCode, and logByte.
  val messageQueue = Module(new Queue(new LogEntry, 16))
  messageQueue.io.enq.valid := io.trigger
  messageQueue.io.enq.bits.messageCode := io.messageCode
  messageQueue.io.enq.bits.logByte := io.logByte  // Capture logByte at enqueue time
  messageQueue.io.deq.ready := false.B

  // Registers for controlling UART transmission.
  val logByteReg = RegInit(0.U(8.W)) // Register to hold the queued logByte value
  val state = RegInit(sIdle)
  val tx_data = RegInit(0.U(8.W))
  val tx_data_valid = RegInit(false.B)
  val tx_cnt = RegInit(0.U(4.W))
  val currentMessageCode = RegInit(0.U(4.W))
  val appendCnt = RegInit(0.U(3.W)) // Counter for appended characters (we need 5 bytes)

  // Periodic timer.
  val periodicTimer = RegInit(0.U(32.W))
  when(periodicTimer < (CLK_FRE * 1000000).U) {
    periodicTimer := periodicTimer + 1.U
  }.otherwise {
    periodicTimer := 0.U
    when(messageQueue.io.enq.ready) {
      messageQueue.io.enq.valid := true.B
      messageQueue.io.enq.bits.messageCode := Logger.Codes.PeriodicMessage
      messageQueue.io.enq.bits.logByte := 0.U  // Default value for periodic messages
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
          currentMessageCode := messageQueue.io.deq.bits.messageCode
          logByteReg := messageQueue.io.deq.bits.logByte  // Use the logByte from the queue
          messageQueue.io.deq.ready := true.B
          state := sSending
          tx_cnt := 0.U
        }.elsewhen(uartRx.io.rx_data_valid && !tx_data_valid) {
          tx_data := uartRx.io.rx_data
          tx_data_valid := true.B
        }
      }
      is(sSending) {
        val msgVec = Wire(Vec(Logger.maxMessageLength, UInt(8.W)))
        val msgLen = WireDefault(0.U(5.W))
        for (i <- 0 until Logger.maxMessageLength) { msgVec(i) := 0.U }
        
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
          } .otherwise {
            // If the message requires an extra byte (e.g. LED toggle), transition to sAppending
            when(currentMessageCode === Logger.Codes.LedToggle) {
              state := sAppending
              appendCnt := 0.U
            } .otherwise {
              tx_cnt := 0.U
              tx_data_valid := false.B
              state := sIdle
            }
          }
        } .otherwise {
          tx_data_valid := true.B
        }
      }
      is(sAppending) {
        // Create a vector for the appended output sequence (5 characters):
        // [0] = space, [1] = '0', [2] = 'x', [3] = high nibble, [4] = low nibble
        val appendedHex = Wire(Vec(5, UInt(8.W)))
        appendedHex(0) := "h20".U  // space
        appendedHex(1) := "h30".U  // '0'
        appendedHex(2) := "h78".U  // 'x'
        
        // Extract high and low nibbles from the captured log byte
        val highNibble = logByteReg(7, 4)
        val lowNibble = logByteReg(3, 0)
        
        // Convert each nibble to its ASCII hex digit
        appendedHex(3) := Mux(highNibble < 10.U, highNibble + "h30".U, highNibble + "h37".U)
        appendedHex(4) := Mux(lowNibble < 10.U, lowNibble + "h30".U, lowNibble + "h37".U)  // Fixed typo here
        
        // Send the appended characters one by one
        tx_data := appendedHex(appendCnt)
        when(tx_data_valid && uartTx.io.tx_data_ready) {
          when(appendCnt < 4.U) {
            appendCnt := appendCnt + 1.U
          } .otherwise {
            // Finished appending extra characters; return to idle
            appendCnt := 0.U
            tx_data_valid := false.B
            state := sIdle
          }
        } .otherwise {
          tx_data_valid := true.B
        }
      }
    }
  }

  uartTx.io.tx_data := tx_data
  uartTx.io.tx_data_valid := tx_data_valid
} 