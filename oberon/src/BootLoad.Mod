MODULE* BootLoad;  (*NW 20.10.2013 / PR 4.2.2014; boot from the disk*)
  IMPORT SYSTEM;
  (* The book's loader. The card is already the way InitSPI would leave it,
     so this body does not bit-bang the init sequence. The switch is the
     button, not the boot source, so the line path stays out. Uart is 0
     for the NOR and 1 for the Dock: the builder compiles each image.

     Each stage stores its code at -84 before the work, and leaves it
     there if the check fails. The codes are published in
     docs/screen-and-boot.md. The 4K holds a short code long enough for
     one whole capture frame. The Dock does not: its UART keeps eight
     words, and a hold while the host is sending would drop the file. *)
  CONST MT = 12; SP = 14;
    MTOrg = 20H; MemLim = 28000H; stackOrg = 18000H;
    Uart = 0;
    wordPort = -72; secPort = -68;
    statusPort = -84;
    spiData = -48; spiCtrl = -44;
    CARD0 = 1; SPIFAST = 4;
    FSoffset = 80000H;
    FlashBase = 200000H; DiskOrg = 29000H;
    Magic = 314B5344H; Version = 1; Build = 0E1H;
    Halt = 0E7FFFFFFH;
    StStarted = 1; StNor = 2; StDdr = 3; StUart = 4;
    StMagic = 5; StBuild = 6; StSum = 7; StCore = 8;
    StInit = 9; StJump = 10;
    Hold = 300000;

  PROCEDURE SPIIdle(n: INTEGER); (*send n FFs slowly with no card selected*)
  BEGIN SYSTEM.PUT(spiCtrl, 0);
    WHILE n > 0 DO DEC(n); SYSTEM.PUT(spiData, -1);
      REPEAT UNTIL SYSTEM.BIT(spiCtrl, 0)
    END
  END SPIIdle;

  PROCEDURE SPI(n: INTEGER); (*send&rcv byte slowly with card selected*)
  BEGIN SYSTEM.PUT(spiCtrl, CARD0); SYSTEM.PUT(spiData, n);
    REPEAT UNTIL SYSTEM.BIT(spiCtrl, 0)
  END SPI;

  PROCEDURE SPICmd(n, arg: INTEGER);
    VAR i, data, crc: INTEGER;
  BEGIN (*send cmd*)
    REPEAT SPIIdle(1); SYSTEM.GET(spiData, data) UNTIL data = 255; (*flush while unselected*)
    REPEAT SPI(255); SYSTEM.GET(spiData, data) UNTIL data = 255; (*flush while selected*)
    IF n = 8 THEN crc := 135 ELSIF n = 0 THEN crc := 149 ELSE crc := 255 END;
    SPI(n MOD 64 + 64); (*send command*)
    FOR i := 24 TO 0 BY -8 DO SPI(ROR(arg, i)) END; (*send arg*)
    SPI(crc); i := 32;
    REPEAT SPI(255); SYSTEM.GET(spiData, data); DEC(i) UNTIL (data < 80H) OR (i = 0)
  END SPICmd;

  PROCEDURE SDShift(VAR n: INTEGER);
    VAR data: INTEGER;
  BEGIN SPICmd(58, 0);  (*CMD58 get card capacity bit*)
    SYSTEM.GET(spiData, data); SPI(-1);
    IF (data # 0) OR ~SYSTEM.BIT(spiData, 6) THEN n := n * 512 END ;  (*non-SDHC card*)
    SPI(-1); SPI(-1); SPIIdle(1)  (*flush response*)
  END SDShift;

  PROCEDURE ReadSD(src, dst: INTEGER);
    VAR i, data: INTEGER;
  BEGIN SDShift(src); SPICmd(17, src); (*CMD17 read one block*)
    i := 0; (*wait for start data marker*)
    REPEAT SPI(-1); SYSTEM.GET(spiData, data); INC(i) UNTIL data = 254;
    SYSTEM.PUT(spiCtrl, SPIFAST + CARD0);
    FOR i := 0 TO 508 BY 4 DO
      SYSTEM.PUT(spiData, -1);
      REPEAT UNTIL SYSTEM.BIT(spiCtrl, 0);
      SYSTEM.GET(spiData, data); SYSTEM.PUT(dst, data); INC(dst, 4)
    END;
    SPI(255); SPI(255); SPIIdle(1) (*may be a checksum; deselect card*)
  END ReadSD;

  PROCEDURE LoadFromDisk;
    VAR src, dst, lim: INTEGER;
  BEGIN src := FSoffset + 4;   (*start at boot block*)
    ReadSD(src, 0); SYSTEM.GET(16, lim);
    INC(src); dst := 512;
    WHILE dst < lim DO ReadSD(src, dst); INC(src); INC(dst, 512) END
  END LoadFromDisk;

  PROCEDURE Word(): INTEGER;
    VAR x: INTEGER;
  BEGIN SYSTEM.GET(wordPort, x); RETURN x
  END Word;

  PROCEDURE Fail;
  BEGIN SYSTEM.PUT(0, Halt)
  END Fail;

  PROCEDURE Pause;
    VAR i: INTEGER;
  BEGIN
    IF Uart = 0 THEN i := Hold; WHILE i > 0 DO DEC(i) END END
  END Pause;

  PROCEDURE Stage(code: INTEGER);
  BEGIN SYSTEM.PUT(statusPort, code); Pause
  END Stage;

  PROCEDURE Check;
    VAR magic, version, build, n, p, sum, want, w: INTEGER;
  BEGIN
    IF Uart = 0 THEN
      Stage(StNor); SYSTEM.PUT(wordPort, FlashBase)
    ELSE
      Stage(StDdr); Stage(StUart)
    END;
    magic := Word(); version := Word(); build := Word(); n := Word(); want := Word();
    Stage(StMagic);
    IF magic # Magic THEN Fail
    ELSE
      Stage(StBuild);
      IF (version # Version) OR (build # Build) OR (n <= 0) OR (n MOD 4 # 0) THEN Fail
      ELSE
        Stage(StSum);
        sum := 0; p := DiskOrg;
        WHILE n > 0 DO
          w := Word();
          IF Uart = 1 THEN SYSTEM.PUT(p, w); INC(p, 4) END;
          sum := sum + w; DEC(n, 4)
        END;
        IF sum # want THEN Fail
        ELSE
          Stage(StCore);
          IF Uart = 1 THEN SYSTEM.PUT(secPort, DiskOrg) ELSE SYSTEM.PUT(secPort, FlashBase + 20) END;
          LoadFromDisk;
          (* The copied image already holds its variables. These stores
             are the init the core still needs: the checksum, MemLim,
             the stack origin, and the heap sentinel. *)
          Stage(StInit);
          (* A disk that ends on a zero beat leaves the Dock bridge busy.
             Address 4 is a zero in the boot image. A 1 there lets the
             checksum store finish. The NOR path does not store it. *)
          IF Uart = 1 THEN SYSTEM.PUT(4, 1) END;
          SYSTEM.PUT(8, sum); SYSTEM.PUT(12, MemLim); SYSTEM.PUT(24, stackOrg);
          SYSTEM.PUT(MemLim, 8); SYSTEM.PUT(MemLim + 4, -1);
          Stage(StJump)
        END
      END
    END
  END Check;

  (* First store: stage 1, mode bit clear. The stack is set before Pause,
     which is the first use of it. The started code is held three times.
     One hold is about a second, and the capture card spends that long
     locking onto the new picture, so a single hold never reaches the file. *)
BEGIN
  SYSTEM.PUT(statusPort, StStarted);
  SYSTEM.LDREG(SP, stackOrg); SYSTEM.LDREG(MT, MTOrg);
  Pause; Pause; Pause; Check
END BootLoad.
