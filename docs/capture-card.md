# HDMI capture card on Bee

UGREEN 15389 (Macrosilicon). USB id `2b89:5389`. This is the Dock HDMI
input, not the Logitech webcam the webcam MCP uses.

| | |
|---|---|
| V4L2 capture | `/dev/video0` |
| V4L2 metadata | `/dev/video1` |
| Card name | `UGREEN 15389: UGREEN 15389` |
| Driver | `uvcvideo` |
| Bus | `usb-0000:00:0d.0-3.1.3` (`ID_PATH=pci-0000:00:0d.0-usb-0:3.1.3:1.0`) |
| Serial | `20230204` |

Checked 4 Nov 2026. Enumerated sizes are the discrete modes below.
`1024x576` is not one of them. A one-frame grab at 21:00 that evening,
with nothing driving the input, came back as a pure black 1024x576 PNG
(ffmpeg scaled the open format). The device was later sitting on
720x480 MJPG.

## Formats

`YUYV` and `MJPG`, same sizes: 2560x1440, 1920x1080, 1600x1200,
1360x768, 1280x1024, 1280x960, 1280x720, 1024x768, 800x600, 720x576,
720x480. Most sizes do 60/50/30/20/10 fps. 2560x1440 tops out at 30.

The Primer 20K Beeb bitstream is 1280x720p60 (74.25 MHz pixel clock).
The card downscales that to the open format. The grab that shows the
boot screen is 720x480 MJPEG. A 27 MHz / 720x576 Beeb stream on the
same cable did not lock. NESTang 720p on this cable did. Both are in
`docs/primer20k/beeb.md`.

Wait a couple of seconds after an SRAM load before grabbing. A frame
taken while the card is locking is black. Opening and closing the
device in a tight loop can also return an MJPEG buffer with no JPEG
data; one frame after the card has locked is the reliable grab.

## Commands

```sh
v4l2-ctl -d /dev/video0 --list-formats-ext
v4l2-ctl -d /dev/video0 --set-fmt-video=width=720,height=480,pixelformat=MJPG
ffmpeg -hide_banner -f v4l2 -input_format mjpeg -video_size 720x480 \
  -i /dev/video0 -frames:v 1 -y /tmp/cap.png
```

One frame with whatever format is already open:

```sh
ffmpeg -hide_banner -f v4l2 -i /dev/video0 -frames:v 1 -y /tmp/cap.png
```

Several frames, a quarter-second apart:

```sh
ffmpeg -hide_banner -f v4l2 -input_format mjpeg -video_size 720x480 \
  -i /dev/video0 -frames:v 8 -vf fps=4 /tmp/beeb-%02d.png
```

`/dev/video1` is metadata only. Do not point the webcam MCP at
`/dev/video0`.
