"""Leather whip drawing from the macOS renderer.

Strokes are emitted in y-up simulation space. A platform flips y when painting.
Geometry matches Sources/main.swift drawWhip, including braid spacing and the
wrapped grip. Clip groups mark strokes that the Mac renderer clips to the grip.
"""

import math

from whip_sim import HANDLE_PIXELS, HandleShape


def _blend(color, fraction, other):
    return tuple(color[i] * (1 - fraction) + other[i] * fraction for i in range(3))


def _cubic(p0, p1, p2, p3, steps=6):
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        points.append((
            u ** 3 * p0[0] + 3 * u ** 2 * t * p1[0] + 3 * u * t ** 2 * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u ** 2 * t * p1[1] + 3 * u * t ** 2 * p2[1] + t ** 3 * p3[1],
        ))
    return points


def whip_strokes(simulation, color, thickness=1.0, handle_shape=HandleShape.STRAIGHT):
    if not simulation.initialized or len(simulation.particles) < 2:
        return []
    color = tuple(color[:3])
    black = (0.0, 0.0, 0.0)
    white = (1.0, 1.0, 1.0)
    hx = math.cos(simulation.handle_angle)
    hy = math.sin(simulation.handle_angle)
    butt = (simulation.particles[0].p.x, simulation.particles[0].p.y)
    ferrule = (butt[0] + hx * HANDLE_PIXELS, butt[1] + hy * HANDLE_PIXELS)
    control = [ferrule]
    chain = 0.0
    previous = (simulation.particles[0].p.x, simulation.particles[0].p.y)
    passed = False
    for particle in simulation.particles[1:]:
        current = (particle.p.x, particle.p.y)
        chain += math.hypot(current[0] - previous[0], current[1] - previous[1])
        previous = current
        if chain < HANDLE_PIXELS:
            continue
        if not passed:
            passed = True
            continue
        control.append(current)
    if len(control) < 2:
        return []
    points = []
    for i in range(len(control) - 1):
        a, b = control[i], control[i + 1]
        for k in range(3):
            t = k / 3
            points.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    points.append(control[-1])

    def width(t):
        return HandleShape.radius(handle_shape, HANDLE_PIXELS) * 1.15 * max(0.0, 1 - t) ** 1.15 + 0.5

    distances = [0.0]
    for i in range(1, len(points)):
        distances.append(distances[-1] + math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]))
    total = max(1.0, distances[-1])
    strokes = []

    def line(a, b, w, ink):
        strokes.append(("line", a[0], a[1], b[0], b[1], w * thickness, ink[0], ink[1], ink[2], ink[3] if len(ink) == 4 else 1.0))

    for i in range(1, len(points)):
        a, b = points[i - 1], points[i]
        t = distances[i] / total
        w = width(t)
        d = max(0.001, math.hypot(b[0] - a[0], b[1] - a[1]))
        normal = (-(b[1] - a[1]) / d, (b[0] - a[0]) / d)
        edge = _blend(color, 0.72, black) + (0.9,)
        body = _blend(color, 0.24, black) + (1.0,)
        line(a, b, w + 1.0, edge)
        line(a, b, w, body)
        shift = w * 0.20 * thickness
        aa = (a[0] + normal[0] * shift, a[1] + normal[1] * shift)
        bb = (b[0] + normal[0] * shift, b[1] + normal[1] * shift)
        line(aa, bb, max(0.3, w * 0.38), _blend(color, 0.22, white) + (1.0,))

    ridge = 4.0
    segment = 1
    while ridge < total * 0.88 and segment < len(distances):
        while segment < len(distances) - 1 and distances[segment] < ridge:
            segment += 1
        if segment >= len(distances):
            break
        a, b = points[segment - 1], points[segment]
        span = max(0.001, distances[segment] - distances[segment - 1])
        f = (ridge - distances[segment - 1]) / span
        center = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        dx = (b[0] - a[0]) / span
        dy = (b[1] - a[1]) / span
        w = width(ridge / total) * 0.46 * thickness

        def local(along, across, center=center, dx=dx, dy=dy):
            return (
                center[0] + dx * along * thickness - dy * across,
                center[1] + dy * along * thickness + dx * across,
            )

        seam = _blend(color, 0.7, black) + (0.85,)
        line(local(-1.25, -w), local(1.1, 0), 0.85, seam)
        line(local(1.1, 0), local(-1.25, w), 0.85, seam)
        line(local(-0.65, -w * 0.85), local(1.65, 0), 0.45, _blend(color, 0.4, white) + (0.8,))
        line(local(1.65, 0), local(-0.65, w * 0.85), 0.45, _blend(color, 0.23, white) + (0.7,))
        ridge += max(2.2, w * 0.95)

    dx, dy = hx, hy

    def grip(along, across=0.0):
        return (
            butt[0] + dx * along - dy * across * thickness,
            butt[1] + dy * along + dx * across * thickness,
        )

    polygon = [grip(0, -HandleShape.radius(handle_shape, 0))]
    r = 1.0
    while r <= HANDLE_PIXELS + 1e-6:
        polygon.append(grip(r, -HandleShape.radius(handle_shape, r)))
        r += 1.0
    tip_radius = HandleShape.radius(handle_shape, HANDLE_PIXELS)
    polygon.extend(_cubic(
        polygon[-1],
        grip(HANDLE_PIXELS + 3, -tip_radius),
        grip(HANDLE_PIXELS + 3, tip_radius),
        grip(HANDLE_PIXELS, tip_radius),
    ))
    r = HANDLE_PIXELS - 1
    while r >= -1e-6:
        polygon.append(grip(r, HandleShape.radius(handle_shape, r)))
        r -= 1.0
    butt_radius = HandleShape.radius(handle_shape, 0)
    polygon.extend(_cubic(
        polygon[-1],
        grip(-3, butt_radius),
        grip(-3, -butt_radius),
        grip(0, -butt_radius),
    ))
    fill = _blend(color, 0.72, black) + (1.0,)
    strokes.append(("fill", polygon, fill[0], fill[1], fill[2], fill[3]))
    strokes.append(("clip", polygon))
    line(grip(0, 1), grip(HANDLE_PIXELS, 1), 7.8, _blend(color, 0.45, black) + (1.0,))
    line(grip(1, 2.6), grip(HANDLE_PIXELS, 2.6), 1.2, _blend(color, 0.12, white) + (0.75,))
    r = 3.0
    while r <= HANDLE_PIXELS - 2 + 1e-6:
        radius = HandleShape.radius(handle_shape, r) * 0.88
        line(grip(r - 1, -radius), grip(r + 1.5, radius), 1.0, _blend(color, 0.85, black) + (1.0,))
        line(grip(r - 0.3, -radius), grip(r + 2.2, radius), 0.55, _blend(color, 0.14, white) + (1.0,))
        r += 3.0
    strokes.append(("unclip",))
    for end in (0.0, HANDLE_PIXELS):
        radius = HandleShape.radius(handle_shape, end) * 0.9
        line(grip(end, -radius), grip(end, radius), 2.1, (0.15, 0.15, 0.15, 1.0))
        line(grip(end + 0.5, -radius), grip(end + 0.5, radius), 0.7, (0.55, 0.55, 0.55, 1.0))
    if simulation.load_amount > 0.02:
        strokes.append((
            "arc", butt[0], butt[1], 14 + thickness * 3,
            90.0, 90.0 + 360.0 * simulation.load_amount, 1.8,
            color[0], color[1], color[2], 0.85,
        ))
    strokes.append(("dot", butt[0], butt[1], 1.3, 1.0, 1.0, 1.0, 0.8))
    if simulation.flash > 0 and points:
        tip = points[-1]
        f = simulation.flash
        for i in range(7):
            angle = i * 2 * math.pi / 7
            inner = 6 + (1 - f) * 15
            outer = inner + f * 16
            line(
                (tip[0] + math.cos(angle) * inner, tip[1] + math.sin(angle) * inner),
                (tip[0] + math.cos(angle) * outer, tip[1] + math.sin(angle) * outer),
                1.8,
                color + (f,),
            )
    return strokes


def paint_tk(canvas, strokes, x_of, y_of, backdrop=(0.075, 0.085, 0.095)):
    """Paint y-up strokes onto a Tk canvas. x_of/y_of map simulation coords.

    Tk has no per-item alpha, so translucent leather is composited over backdrop.
    """
    canvas.delete("whip")
    clip = None
    for stroke in strokes:
        kind = stroke[0]
        if kind == "clip":
            flat = []
            for x, y in stroke[1]:
                flat.extend((x_of(x), y_of(y)))
            if len(flat) >= 6:
                clip = canvas.create_polygon(*flat, fill="", outline="", tags=("whip", "clip"))
            continue
        if kind == "unclip":
            clip = None
            continue
        if kind == "fill":
            flat = []
            for x, y in stroke[1]:
                flat.extend((x_of(x), y_of(y)))
            if len(flat) >= 6:
                canvas.create_polygon(
                    *flat,
                    fill=_hex(stroke[2], stroke[3], stroke[4], stroke[5], backdrop),
                    outline="",
                    tags="whip",
                )
            continue
        if kind == "line":
            _, x1, y1, x2, y2, width, r, g, b, a = stroke
            canvas.create_line(
                x_of(x1), y_of(y1), x_of(x2), y_of(y2),
                width=max(0.4, width),
                fill=_hex(r, g, b, a, backdrop),
                capstyle="round",
                joinstyle="round",
                tags="whip",
            )
            continue
        if kind == "dot":
            _, x, y, radius, r, g, b, a = stroke
            cx, cy = x_of(x), y_of(y)
            canvas.create_oval(
                cx - radius, cy - radius, cx + radius, cy + radius,
                fill=_hex(r, g, b, a, backdrop), outline="", tags="whip",
            )
            continue
        if kind == "arc":
            _, cx, cy, radius, start, end, width, r, g, b, a = stroke
            # AppKit y-up degrees, counter-clockwise from start to end.
            # Tk's create_arc uses y-down, so the sweep is negated to stay
            # counter-clockwise on screen, starting at 12 o'clock.
            sx, sy = x_of(cx), y_of(cy)
            extent = -(end - start)
            canvas.create_arc(
                sx - radius, sy - radius, sx + radius, sy + radius,
                start=start, extent=extent,
                style="arc",
                width=max(0.6, width),
                outline=_hex(r, g, b, a, backdrop),
                tags="whip",
            )


def _hex(r, g, b, a=1.0, backdrop=(0.075, 0.085, 0.095)):
    def channel(v):
        return max(0, min(255, int(round(v * 255))))
    if a >= 0.999:
        return f"#{channel(r):02x}{channel(g):02x}{channel(b):02x}"
    r = r * a + backdrop[0] * (1 - a)
    g = g * a + backdrop[1] * (1 - a)
    b = b * a + backdrop[2] * (1 - a)
    return f"#{channel(r):02x}{channel(g):02x}{channel(b):02x}"
