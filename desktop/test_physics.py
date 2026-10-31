"""Lock the Windows, Linux, and web ports to the macOS physics dump."""

import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from whip_draw import whip_strokes
from whip_prefs import colors_match
from whip_sim import (
    COUNT,
    REST_ANGLE,
    CrackTiming,
    HandleShape,
    Point,
    WhipGesture,
    WhipSimulation,
    clamped,
    run_golden_script,
)

GOLDEN = Path(__file__).resolve().parent / "physics-golden.txt"


def check_golden():
    snaps = run_golden_script()
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(snaps)
    worst = 0.0
    for line, (tag, count, values) in zip(lines, snaps):
        parts = line.split()
        assert parts[0] == tag
        assert int(parts[1]) == count == COUNT
        golden = [float(item) for item in parts[2:]]
        assert len(golden) == len(values)
        for got, expected in zip(values, golden):
            worst = max(worst, abs(got - expected))
    assert worst < 1e-8, worst
    return worst


def check_gestures():
    for _name in ("left", "right"):
        timing = CrackTiming()
        first = timing.next_start(10.0)
        second = timing.next_start(10.025)
        assert first < second and second - first >= 0.0949
        assert second < 10.13
        assert abs(timing.next_start(11.0) - 11.006) < 0.0001
    for button in (0, 1):
        gesture = WhipGesture()
        assert gesture.press(button, 1, False)
        assert gesture.release(button, 1.02, False) is None
        assert gesture.press(button, 1.1, False)
        assert gesture.release(button, 1.12, False) is None
        assert not gesture.press(button, 2, True)
        assert gesture.charge(2.45, True) > 0.49
        assert gesture.release(button, 3, True) == 1
        assert gesture.release(button, 3.1, True) is None
        for moment in (4.0, 4.1):
            assert not gesture.press(button, moment, True)
            assert gesture.release(button, moment + 0.025, True) is not None
        gesture.press(button, 5, True)
        gesture.cancel()
        assert gesture.charge(6, True) == 0
        assert gesture.release(button, 6, True) is None
    simulation = WhipSimulation()
    for _ in range(240):
        simulation.step(Point(200, 200), 170, 1)
    assert simulation.load_amount > 0.99
    simulation.crack(1.65)
    for _ in range(120):
        simulation.step(Point(200, 200), 170)
    assert all(math.isfinite(p.p.x) and math.isfinite(p.p.y) for p in simulation.particles)
    assert abs(simulation.handle_angle - REST_ANGLE) < 0.25
    simulation.crack(1.4)
    assert simulation.handle_angular_velocity < 0
    assert len({HandleShape.radius(shape, 0) for shape in HandleShape.ALL}) == 3
    assert clamped(-1, 0, 1) == 0 and clamped(2, 0, 1) == 1
    assert colors_match((0.96, 0.47, 0.26), (0.961, 0.472, 0.258))
    assert not colors_match((0.96, 0.47, 0.26), (0.40, 0.76, 1))


def check_strokes_match_web():
    node = subprocess.run(
        ["node", str(ROOT / "web" / "check-physics.js"), "--strokes"],
        check=False,
        capture_output=True,
        text=True,
    )
    if node.returncode != 0:
        raise SystemExit(node.stderr or node.stdout)
    web = json.loads(node.stdout)
    simulation = WhipSimulation()
    for i in range(180):
        t = i / 60
        simulation.step(Point(500 + math.sin(t) * 200, 500 + math.cos(t * 2) * 100), 340)
        if i == 40:
            simulation.crack()
    for _ in range(240):
        simulation.step(Point(200, 200), 340, 1)
    strokes = whip_strokes(simulation, (0.96, 0.47, 0.26), 1.0, "flared")
    numbers = _flatten(strokes)
    assert len(numbers) == len(web)
    worst = max(abs(a - b) for a, b in zip(numbers, web))
    assert worst < 1e-8, worst


def _flatten(strokes):
    numbers = []
    for stroke in strokes:
        if stroke[0] == "line":
            numbers.extend(stroke[1:10])
        elif stroke[0] in ("fill", "clip"):
            for point in stroke[1]:
                numbers.extend(point)
        elif stroke[0] in ("arc", "dot"):
            numbers.extend(stroke[1:])
    return numbers


if __name__ == "__main__":
    worst = check_golden()
    check_gestures()
    check_strokes_match_web()
    print(f"PASS: physics matches macOS within {worst:.2e}")
    print("PASS: clicks, loaded releases, double-clicks, handles, stroke geometry")
