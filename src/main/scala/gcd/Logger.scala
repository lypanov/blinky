package gcd

import chisel3._
import chisel3.util._
import scala.language.experimental.macros
import scala.reflect.macros.blackbox
import chisel3.util.MuxLookup

/** A simple definition of a log message.
  * @param code the 4-bit message code that can be used in hardware
  * @param text the associated message text (will be converted to a vector of UInts)
  * @param renderLogByte a boolean flag indicating whether the log byte should be rendered
  */
case class LogMessage(code: UInt, text: String, renderLogByte: Boolean)

/** A bundle that represents a log entry to be sent to the Logger */
class LogEntry extends Bundle {
  val messageCode = UInt(4.W) // 4-bit code to identify the message type
  val logByte = UInt(32.W)     // 8-bit data payload
  val logByte1 = UInt(8.W)    // 8-bit data payload
}

/** A trait that defines the interface for a log producer */
trait LogProducer extends Module {
  val logOut: DecoupledIO[LogEntry]
}

object Logger {
  // Centralized list of available messages.
  val messages: Seq[LogMessage] = Seq(
    LogMessage(0.U(4.W), "Led:   ", true),
    LogMessage(1.U(4.W), "Ping   ", false),
    LogMessage(2.U(4.W), "MD:    ", true),
  )

  // Extracting named constants from our messages list.
  object Codes {
    val LedToggle = messages(0).code  // Used for LED events (with an attached value)
    val PeriodicMessage = messages(1).code
    val MemoryDump = messages(2).code
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
    * This method creates a log entry and enqueues it to the producer's queue.
    *
    * @param producer the LogProducer to send the log entry to
    * @param messageCode the log message code from Logger.Codes
    * @param value the extra 8-bit value to be sent with the message
    */
  def log(producer: LogProducer, messageCode: UInt, value: UInt): Unit = {
    val entry = Wire(new LogEntry)
    entry.messageCode := messageCode
    entry.logByte := value
    
    // Only enqueue if the queue is ready to accept new entries
    when(producer.logOut.ready) {
      producer.logOut.valid := true.B
      producer.logOut.bits := entry
    }
  }
  
  /** Convenience method for logging with default value of 0 */
  def log(producer: LogProducer, messageCode: UInt): Unit = {
    log(producer, messageCode, 0.U(8.W))
  }
  
  /** Legacy logging interface for backward compatibility.
    *
    * This method sets the "trigger" high and assigns the provided message code to "messageCode"
    * inside the passed io Bundle.
    *
    * @param io the IO bundle containing a "trigger" and "messageCode" signal.
    * @param messageCode the log message code from Logger.Codes.
    * @param value the extra 8-bit value to be sent with the message
    */
  def log(io: Bundle, messageCode: UInt, value: UInt): Unit = {
    // Retrieve the "trigger", "messageCode", and our new "logByte" signals from the IO Bundle.
    val trigger = io.elements.get("trigger").get.asInstanceOf[Bool]
    val msgCode = io.elements.get("messageCode").get.asInstanceOf[UInt]
    val logByte = io.elements.get("logByte").get.asInstanceOf[UInt]

    trigger := true.B
    msgCode := messageCode
    logByte := value
  }
  
  /** Convenience method for legacy logging with default value of 0 */
  def log(io: Bundle, messageCode: UInt): Unit = {
    log(io, messageCode, 0.U(8.W))
  }
}

/** A simple log producer that can be used to generate periodic messages */
class SimpleLogProducer(queueDepth: Int = 8) extends Module with LogProducer {
  val io = IO(new Bundle {
    val trigger = Input(Bool())
    val messageCode = Input(UInt(4.W))
    val logByte = Input(UInt(32.W))
  })
  
  // Create a queue for log entries
  val logQueue = Module(new Queue(new LogEntry, queueDepth))
  
  // Define logOut as an IO port to satisfy the LogProducer trait
  val logOut = IO(Decoupled(new LogEntry))
  
  // Connect the internal queue's dequeue interface to the logOut port
  logOut <> logQueue.io.deq
  
  // Connect the queue input
  logQueue.io.enq.valid := io.trigger
  logQueue.io.enq.bits.messageCode := io.messageCode
  logQueue.io.enq.bits.logByte := io.logByte
  logQueue.io.enq.bits.logByte1 := 0.U
}

class Logger(numProducers: Int = 1, clkFreq: Int = 27, uartFreq: Int = 57600) extends Module { // 115200
  val io = IO(new Bundle {
    val clk = Input(Clock())
    val rst_n = Input(Bool())
    val producerLogs = Vec(numProducers, Flipped(Decoupled(new LogEntry)))
    val uart_rx = Input(Bool())
    val uart_tx = Output(Bool())
  })

  val CLK_FRE = clkFreq
  val UART_FRE = uartFreq

  val sIdle    = 0.U(2.W)
  val sSending = 1.U(2.W)
  val sAppending = 2.U(2.W)  // State for appending the hex log byte

  val uartRx = Module(new UartRx(CLK_FRE, UART_FRE))
  val uartTx = Module(new UartTx(CLK_FRE, UART_FRE))

  uartRx.io.clk := io.clk
  uartRx.io.rst_n := io.rst_n
  uartRx.io.rx_pin := io.uart_rx
  uartRx.io.rx_data_ready := true.B

  uartTx.io.clk := io.clk
  uartTx.io.rst_n := io.rst_n
  io.uart_tx := uartTx.io.tx_pin

  // Internal queue for periodic messages
  val internalProducer = Module(new SimpleLogProducer())
  val periodicTimer = RegInit(0.U(32.W))
  
  internalProducer.io.trigger := false.B
  internalProducer.io.messageCode := Logger.Codes.PeriodicMessage
  internalProducer.io.logByte := 0.U
  
  when(periodicTimer < (CLK_FRE * 1000000).U) {
    periodicTimer := periodicTimer + 1.U
  }.otherwise {
    periodicTimer := 0.U
    // internalProducer.io.trigger := true.B
  }

  // Arbiter to select from producer queues + internal queue
  val arbiter = Module(new Arbiter(new LogEntry, numProducers + 1))
  
  // Connect producer logs to arbiter inputs
  for (i <- 0 until numProducers) {
    arbiter.io.in(i) <> io.producerLogs(i)
  }
  
  // Connect internal producer to the last arbiter input
  arbiter.io.in(numProducers) <> internalProducer.logOut
  
  // Registers for controlling UART transmission
  val logByteReg = RegInit(0.U(32.W))
  val state = RegInit(sIdle)
  val tx_data = RegInit(0.U(8.W))
  val tx_data_valid = RegInit(false.B)
  val tx_cnt = RegInit(0.U(4.W))
  val currentMessageCode = RegInit(0.U(4.W))
  val appendCnt = RegInit(0.U(4.W)) // Counter for appended characters (now needs 11 states)
  val tx_data_valid_reg = RegInit(false.B) // Register to control tx_data_valid

  // Default values
  arbiter.io.out.ready := false.B

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
        when(arbiter.io.out.valid) {
          currentMessageCode := arbiter.io.out.bits.messageCode
          logByteReg := arbiter.io.out.bits.logByte
          arbiter.io.out.ready := true.B
          state := sSending
          tx_cnt := 0.U
        }.elsewhen(uartRx.io.rx_data_valid && !tx_data_valid) {
          tx_data := uartRx.io.rx_data
          tx_data_valid := true.B
        }
      }
      is(sSending) {
        val msgVec = Wire(Vec(Logger.maxMessageLength, UInt(8.W)))
        val msgLen = 9.U(5.W) // WireDefault(0.U(5.W))
        for (i <- 0 until Logger.maxMessageLength) { msgVec(i) := 0.U }
        
        val messageData = Logger.messages.map { msg =>
          val (vec, len) = Logger.createMessage(msg.text)
          (msg.code, vec, len)
        }

        messageData.foldLeft(when(false.B) {}) { case (acc, (code, vec, len)) =>
          acc.elsewhen(currentMessageCode === code) {
            for (i <- 0 until vec.length) { msgVec(i) := vec(i) }
            // msgLen := len
          }
        }

        tx_data := msgVec(tx_cnt)
        when(tx_data_valid && uartTx.io.tx_data_ready) {
          when(tx_cnt < (msgLen - 1.U)) {
            tx_cnt := tx_cnt + 1.U
          } .otherwise {
            // If the message requires an extra byte (e.g. LED toggle), transition to sAppending
            // Replace hard-coded check with a dynamic lookup using the renderLogByte flag from the LogMessage definition.
            /*
            val renderFlag = MuxLookup(currentMessageCode, false.B)(
              Logger.messages.map { msg => (msg.code, msg.renderLogByte.B) }
            )
            */
            val renderFlag = true.B

            when(tx_cnt < (msgLen - 1.U)) {
              tx_cnt := tx_cnt + 1.U
            } .otherwise {
              when(renderFlag) {
                state := sAppending
                appendCnt := 0.U
              } .otherwise {
                tx_cnt := 0.U
                tx_data_valid := false.B
                state := sIdle
              }
            }
          }
        } .otherwise {
          tx_data_valid := true.B
        }
      }
      is(sAppending) {
        // Create a vector for the appended output sequence (11 characters):
        // [0] = space, [1] = '0', [2] = 'x', [3-10] = 8 hex digits
        val appendedHex = Wire(Vec(11, UInt(8.W)))
        appendedHex(0) := "h20".U  // space
        appendedHex(1) := "h30".U  // '0'
        appendedHex(2) := "h78".U  // 'x'
        
        // Extract all 8 nibbles from the 32-bit log byte
        for (i <- 0 until 8) {
          val nibble = logByteReg(31 - (i*4), 28 - (i*4))
          appendedHex(3 + i) := Mux(nibble < 10.U, nibble + "h30".U, nibble + "h37".U)
        }
        
        // Send the appended characters one by one
        tx_data := appendedHex(appendCnt)
        tx_data_valid_reg := false.B // Default to false
        when(uartTx.io.tx_data_ready) {
          tx_data_valid_reg := true.B // Assert tx_data_valid only when UART is ready
          when(appendCnt < 10.U) {
            appendCnt := appendCnt + 1.U
          } .otherwise {
            // Finished appending extra characters; return to idle
            appendCnt := 0.U
            state := sIdle
          }
        }
      }
    }
  }

  uartTx.io.tx_data := tx_data
  uartTx.io.tx_data_valid := tx_data_valid_reg // Use the registered tx_data_valid
} 