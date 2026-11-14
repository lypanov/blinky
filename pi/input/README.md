# Pi input box

Status: planning. No code yet. Owner of this file: the project coordinator (PM thread).

## Goal

A Raspberry Pi 400 is the single input and network box for the boards. The FPGAs never deal with USB, Bluetooth or TLS themselves.

## Decided

- **Link to the Dock:** the Pi 400 connects to the Primer 20K Dock over USB, using the Dock's USB UART. Same cable programs the Dock.
- **Keyboards:** both are allowed. The Avatto A20 folding Bluetooth keyboard (normal use, Pi sits in a corner as a hub) and the Pi 400's own keyboard (demos).
- **Pointer:** a Logitech trackball paired to the Pi over Bluetooth, so it can be flipped between devices. No RF dongle.
- **Mouse:** a Bluetooth mouse will be paired later (for demos away from home); needs pairing support on the Pi. Not now.
- **Networking:** partial offload. Dock hardware does framing, escaping, packet buffers and checksums; Oberon runs a tiny IP/UDP/TCP stack and a Gemini client. The Pi forwards packets and terminates TLS. The serial link is called SLIP.
- **Link to the 4K:** later, as the final physical project: three soldered header pins, a resistor divider (Pi 3.3 V to 4K 1.8 V) on a separate small breadboard, DuPont jumpers to the Pi's GPIO. Same byte protocol on every link.
- **Power:** one USB-C in. The Pi 400 has likely powered the Dock before, via a hub; to confirm when the hub is free.

## Where the detail lives

- Reboot-to-load and UART framing: Oberon queue items 48+ (planned in the "4K space for console" chat, PR #104). The queue is authoritative; byte sequences changed over time and the queue holds the current one.
- Ideation chats are brainstorm only. Anything not in a `todo.md` is not decided.

## Open

- Pi-side software: language, how it maps key/mouse events to bytes, Bluetooth pairing flow. Not discussed yet.
- Pi notes currently held in Grokbot need to be moved here.
