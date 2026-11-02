#!/usr/bin/env python3
"""Offline launcher for the 'Field from Above' demo page.

The demo page is a single static HTML file. It never calls the network and
never reads an API key. This launcher only explains which mode you get.

    python demo/uruchom_demo.py            # offline demo, no key needed
    python demo/uruchom_demo.py --serwuj   # serve on http://127.0.0.1:8765
    python demo/uruchom_demo.py --tryb api # check the API key only

The API key is read from the META_API_KEY environment variable and is never
printed. The full application (not part of this repository) is the only place
that can call the Meta Model API.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

STRONA = Path(__file__).resolve().parent / "index.html"
KOMUNIKAT_BRAK = (
    "META_API_KEY is not set — the offline demo still works. "
    "Only the live Meta API call is unavailable."
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Field from Above — offline demo")
    parser.add_argument("--serwuj", action="store_true",
                        help="serve the page on 127.0.0.1:8765 (local only)")
    parser.add_argument("--tryb", choices=["lokalny", "api"], default="lokalny",
                        help="lokalny = offline page; api = check the key only")
    args = parser.parse_args()

    if not STRONA.is_file():
        print(f"ERROR: demo page not found: {STRONA}", file=sys.stderr)
        return 2

    klucz = os.environ.get("META_API_KEY", "").strip()

    if args.tryb == "api":
        if not klucz:
            print("ERROR: " + KOMUNIKAT_BRAK, file=sys.stderr)
            return 2
        print("META_API_KEY is set (value not printed).")
        print("This repository ships no API client. The full application is what calls "
              "the Meta Model API; the demo page stays offline.")
        return 0

    print("Field from Above — demo")
    print("Mode: offline (no network, no API key)")
    print(f"Page: {STRONA}")
    if klucz:
        print("META_API_KEY is set, but this page does not use it.")
    else:
        print(KOMUNIKAT_BRAK)

    if args.serwuj:
        import http.server
        import socketserver

        os.chdir(STRONA.parent)
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("127.0.0.1", 8765), handler) as httpd:
            print("Serving on http://127.0.0.1:8765 — press Ctrl+C to stop.")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
