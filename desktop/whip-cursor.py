#!/usr/bin/env python3
"""Windows and Linux Whip Cursor. macOS keeps using Whip Cursor.app."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from whip_app import main

if __name__ == "__main__":
    raise SystemExit(main())
