"""Appearance settings. Same keys, ranges, and defaults as the macOS app.

The desktop whip starts off on every launch. That switch is not stored.
"""

import json
import os
import sys
from pathlib import Path

from whip_sim import (
    DEFAULT_COLOR,
    LENGTH_DEFAULT,
    LENGTH_MAX,
    LENGTH_MIN,
    SWATCHES,
    THICKNESS_DEFAULT,
    THICKNESS_MAX,
    THICKNESS_MIN,
    VOLUME_DEFAULT,
    CrackStyle,
    HandleShape,
    clamped,
)


def colors_match(a, b, epsilon=0.02):
    return all(abs(a[i] - b[i]) < epsilon for i in range(3))


def settings_path():
    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or str(Path.home())
        return Path(root) / "WhipCursor" / "settings.json"
    return Path.home() / ".config" / "whip-cursor" / "settings.json"


class Preferences:
    def __init__(self):
        self.enabled = False
        self.handle_shape = HandleShape.STRAIGHT
        self.load_mode = False
        self.replace_pointer = True
        self.replacement_available = True
        self.pause_shortcut_available = True
        self.crack_style = CrackStyle.CLASSIC
        self.sound = True
        self.volume = VOLUME_DEFAULT
        self.thickness = THICKNESS_DEFAULT
        self.length = LENGTH_DEFAULT
        self.color = DEFAULT_COLOR
        self.listeners = []

    def load(self):
        path = settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        shape = data.get("handleShape", "")
        if shape in HandleShape.ALL:
            self.handle_shape = shape
        style = data.get("crackStyle", "")
        if style in CrackStyle.ALL:
            self.crack_style = style
        if isinstance(data.get("loadMode"), bool):
            self.load_mode = data["loadMode"]
        if isinstance(data.get("replacePointer"), bool):
            self.replace_pointer = data["replacePointer"]
        if isinstance(data.get("sound"), bool):
            self.sound = data["sound"]
        if isinstance(data.get("volume"), (int, float)):
            self.volume = clamped(float(data["volume"]), 0, 1)
        if isinstance(data.get("length"), (int, float)):
            self.length = clamped(float(data["length"]), LENGTH_MIN, LENGTH_MAX)
        if isinstance(data.get("thickness"), (int, float)):
            self.thickness = clamped(float(data["thickness"]), THICKNESS_MIN, THICKNESS_MAX)
        color = data.get("color")
        if isinstance(color, list) and len(color) == 3 and all(isinstance(c, (int, float)) for c in color):
            self.color = tuple(clamped(float(c), 0, 1) for c in color)

    def save(self):
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "handleShape": self.handle_shape,
            "loadMode": self.load_mode,
            "replacePointer": self.replace_pointer,
            "crackStyle": self.crack_style,
            "sound": self.sound,
            "volume": self.volume,
            "thickness": self.thickness,
            "length": self.length,
            "color": list(self.color),
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def touch(self):
        self.save()
        for listener in list(self.listeners):
            listener()

    def matches_swatch(self, swatch):
        return colors_match(self.color, swatch)


SWATCH_NAMES = tuple(name for name, _ in SWATCHES)
