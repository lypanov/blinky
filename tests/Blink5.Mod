MODULE Blink5;
  IMPORT MMT := AMemoryMappedToggle;
  VAR counter, maxIterations: INTEGER;
BEGIN
  counter := 0;
  maxIterations := 65536;
  WHILE TRUE DO
    INC(counter);
    IF counter >= maxIterations THEN
      MMT.Toggle;
      counter := 0
    END
  END
END Blink5.
