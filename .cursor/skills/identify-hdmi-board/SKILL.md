---
name: identify-hdmi-board
description: >-
  Tell which FPGA has the HDMI cable from a lit-room webcam still.
  Use before HDMI capture, after a load, or when the capture-card
  picture might be the wrong board. The Dock is the upper metal
  case; the Nano 4K is the lower one. Skip when the room is dark.
---

There is one HDMI cable. The maintainer moves it. Do not trust a remembered
size, a frozen picture, or which board was last loaded.

## Room light

This check needs the desk lamp on. Sleep is around 00:00 Europe/Amsterdam;
outside working hours the room is usually dark and there is nothing to do.

1. Restore the scene knobs, then `capture_still` on `/dev/video2`:
   `auto_exposure=1`, `gain=96`, `exposure=100`, `brightness=200`,
   `contrast=64`.
2. If mean luma is under 25, or the metal cases and cables are not visible,
   the light is off. Stop. Do not guess the cable. `auto_adjust` is the LED
   profile; it crushes the desk on purpose and is not this check.

## Which board is which

Call webcam MCP `check_all` or `detect_leds` on `/dev/video2`. The detector
assigns **upper = primer20k / Dock** and **lower = nano4k**. Then look at
the scene still, not the dark `auto_adjust` frame.

- **Dock (20K):** upper case. A thick black HDMI cable enters its right
  side. The small HDMI monitor sits to the right of that case.
- **Nano 4K:** lower case. USB-C only. No thick HDMI cable.

If `check_all` names the upper cluster `primer20k` and the scene still shows
HDMI in that same case, the capture card is on the Dock: YUYV **1024×768**.
If HDMI is absent from the upper case, the cable is on the 4K: YUYV
**720×480**.

`auto_adjust` / `check_all` change exposure. Put the scene knobs back and
take one more still before judging cables.

## MCP

On Cursor desktop, tools are `list_cameras`, `capture_still`, `auto_adjust`,
`detect_leds`, `measure_blink`, `check_all` at `http://127.0.0.1:8766/mcp`.
A cloud agent on this machine may not see those tools in its catalog. Call
the same URL with the MCP HTTP client. Do not import `server.py`. Do not run
`measure_blink` on `/dev/video0` (that is the HDMI stick).
