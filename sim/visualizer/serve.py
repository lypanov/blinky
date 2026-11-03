#!/usr/bin/env python3
"""Tiny static server for the Blink2 visualizer (Arch / macOS / anything with Python 3)."""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import socketserver
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()

    os.chdir(HERE)
    socketserver.TCPServer.allow_reuse_address = True
    handler = functools.partial(Handler, directory=HERE)
    with socketserver.TCPServer((args.bind, args.port), handler) as httpd:
        url = f"http://{args.bind}:{args.port}/"
        print(f"Blink2 visualizer at {url}", flush=True)
        print("Ctrl-C to stop.", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
