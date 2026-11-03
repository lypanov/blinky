MODULE Blink;
VAR
  counter: INTEGER;
  led: INTEGER;

BEGIN
  counter := 1000000;
  led := 0;
  
  WHILE TRUE DO
    DEC(counter);
    IF counter = 0 THEN
      IF led = 0 THEN
        led := 1;
      ELSE
        led := 0;
      END;
      counter := 1000000;
    END;
  END;
END Blink.

