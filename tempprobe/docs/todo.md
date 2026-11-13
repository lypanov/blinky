# Temperature probe on the TTGO T8

1. Detect the board over USB. Passed. No CH9102F (1a86:55d4) is on the bus. The port the MaixDock used (USB 1-1.3) has a Silicon Labs CP2104, serial 016AB8CF, attached at 15:04. Other serial devices: Espressif JTAG on /dev/ttyACM0, and a second CP2104 (serial 0214228B) on /dev/ttyUSB0. The 016AB8CF CP2104 was confirmed as the TTGO.
2. Write and flash a minimal sketch that scans GPIO 4 for a DS18B20 and prints the temperature in Celsius once per second. Passed. ESP-IDF 5.5.6 project at tempprobe/ds18b20, flashed to the CP2104 by-id path for serial 016AB8CF.
3. Report what the serial monitor shows. Passed. 1 device, ROM 28 FF 6A 0E 85 16 04 81, 18.88 C (11 samples, all 18.88 C). Ice pass: from 15:27:25 at 1.50 C down steadily to 15:28:23 at -0.25 C (still falling). Samples: 15:27:38 1.00 C, 15:27:52 0.50 C, 15:28:11 0.00 C. No -127, no 85. The image header still says 2 MB while the chip has 4 MB, and that was left unchanged.
