# Physics lock

The macOS app in `Source/Sources/main.swift` is the source of the whip. Windows, Linux, and web/whip.js copy that behavior. They do not invent a second rope.

## What stays put

These values are the product, not suggestions:

| Setting | Value |
| --- | --- |
| Particles | 40 |
| Rest angle | π/3, y-up |
| Handle length | 46 px |
| Whip length | 180–540, default 340 |
| Thickness | 0.5–2.5, default 1 |
| Load time for a full charge | 0.9 s |
| Crack strength | 1 + charge × 0.65 |
| Fastest gap between crack sounds | 95 ms, with a 6 ms onset |
| Preview length | 72% of the desktop length |
| Jump reset | cursor moved more than 1100 px |

Handle radii:

- Straight: 5.5
- Tapered: 6.5 − 2.2t
- Flared: 4.4 + 2.7(1−t)³ + 1.3t⁶

`desktop/physics-golden.txt` is a dump from the optimized macOS binary (`--physics-golden`). `desktop/test_physics.py` and `web/check-physics.js` replay the same script. A difference above 1e-8 is a port bug, not a new look.

## Coordinates

The simulation lives in macOS space: x right, y up. A crack throws the thong and the hang falls toward negative y.

Windows, Linux, and the browser read a top-left pointer. They convert with `y_up = -y_down` for the desktop, or `y_up = height - y_down` inside a view, run the same step, and flip back when drawing. Do not rewrite the angles for a y-down canvas.

## Drawing

`drawWhip` in the Swift file, `desktop/whip_draw.py`, and `whipStrokes` in `web/whip.js` emit the same leather strokes: dark edge, dyed body, highlight, chevron braid, wrapped grip, charge ring, white click dot, and the seven-ray pop. The web and Python stroke lists are compared on a loaded, flared frame.

## Settings that are not the rope

The on/off switch starts off and is not saved. Color, length, thickness, handle, sound, volume, hold-to-load, and “replace the pointer” are saved per machine.
