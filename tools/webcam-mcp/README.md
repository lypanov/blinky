# Webcam MCP

Small streamable-HTTP MCP server so Cursor agents on Bee can grab webcam stills
(FPGA LEDs, HDMI monitor) without holding `/dev/video0`. Same capture path as
`tools/webcam_still.sh`: `ffmpeg -f v4l2`, one JPEG, then the device is closed.

Listens on **127.0.0.1:8766** (`/mcp`). Port 8765 is already the Blink2
visualizer (`tools/run_visualizer.sh`).

Does not touch the FPGA, serial ports, or `openFPGALoader`.

## Tools

| Tool | What it does |
|---|---|
| `list_cameras` | V4L2 `/dev/videoN` nodes and kernel names (no device open) |
| `capture_still` | One JPEG: MCP image content + path under `~/fpga/captures/` |
| `capture_burst` | N stills at an interval; returns paths only |

`capture_still` arguments: `device` (default `/dev/video0`), optional
`resolution` (`640x480`), optional `warmup_frames` (default 8, discard AE
settle frames; `0` matches `webcam_still.sh`).

Camera access is serialised with an `flock` on `$XDG_RUNTIME_DIR/webcam-mcp.lock`.
ffmpeg is started and waited on per shot, so the V4L2 node is free afterwards
and `tools/measure_blink.sh` can run in between.

A later HDMI capture stick (UGREEN 15389, UVC) will show up from
`list_cameras`; pass its `/dev/videoN` as `device`.

## Install (once)

From this directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p ~/.config/systemd/user
ln -sfn "$PWD/webcam-mcp.service" ~/.config/systemd/user/webcam-mcp.service
systemctl --user daemon-reload
systemctl --user enable --now webcam-mcp.service
```

Start at boot without logging in (needs sudo, one shot):

```sh
sudo loginctl enable-linger lypanov
```

Cursor on Bee: `~/.cursor/mcp.json` should contain (keep any other servers):

```json
{
  "mcpServers": {
    "webcam": {
      "url": "http://127.0.0.1:8766/mcp"
    }
  }
}
```

## How agents use it

Call `list_cameras`, then `capture_still` with the Logitech (`/dev/video0`) or
the HDMI stick. The still is returned as an image the model can see, and a
timestamped JPEG is left in `~/fpga/captures/`.

```sh
systemctl --user status webcam-mcp.service
systemctl --user restart webcam-mcp.service
journalctl --user -u webcam-mcp.service -e
```
