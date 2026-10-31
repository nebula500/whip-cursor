"""Rope physics from the macOS app. Same constants, same step order.

Coordinates are y-up, matching AppKit. Platforms flip y only when drawing
or when reading a top-left cursor.
"""

import math

COUNT = 40
REST_ANGLE = math.pi / 3
HANDLE_PIXELS = 46.0
THROAT_PIXELS = 36.0

LENGTH_MIN = 180.0
LENGTH_MAX = 540.0
LENGTH_DEFAULT = 340.0
THICKNESS_MIN = 0.5
THICKNESS_MAX = 2.5
THICKNESS_DEFAULT = 1.0
VOLUME_DEFAULT = 0.45

SWATCHES = (
    ("Ember", (0.96, 0.47, 0.26)),
    ("Mint", (0.42, 0.89, 0.72)),
    ("Lavender", (0.68, 0.58, 1.0)),
    ("Ice", (0.40, 0.76, 1.0)),
    ("Rose", (1.0, 0.48, 0.66)),
    ("Pearl", (0.94, 0.94, 0.88)),
)
DEFAULT_COLOR = SWATCHES[0][1]


def clamped(value, lo, hi):
    return min(hi, max(lo, value))


class Point:
    def __init__(self, x=0.0, y=0.0):
        self.x = float(x)
        self.y = float(y)

    def copy(self):
        return Point(self.x, self.y)


class Particle:
    def __init__(self, p):
        self.p = p
        self.previous = p.copy()


class HandleShape:
    STRAIGHT = "straight"
    TAPERED = "tapered"
    FLARED = "flared"
    ALL = (STRAIGHT, TAPERED, FLARED)
    TITLES = {STRAIGHT: "Straight", TAPERED: "Tapered", FLARED: "Flared"}

    @staticmethod
    def radius(shape, distance):
        t = min(1.0, max(0.0, distance / HANDLE_PIXELS))
        if shape == HandleShape.STRAIGHT:
            return 5.5
        if shape == HandleShape.TAPERED:
            return 6.5 - 2.2 * t
        return 4.4 + 2.7 * (1 - t) ** 3 + 1.3 * t ** 6


class CrackStyle:
    CLASSIC = "classic"
    SHARP = "sharp"
    DRY = "dry"
    CINEMATIC = "cinematic"
    ALL = (CLASSIC, SHARP, DRY, CINEMATIC)
    TITLES = {
        CLASSIC: "Classic bullwhip",
        SHARP: "Sharp snap",
        DRY: "Dry crack",
        CINEMATIC: "Swoosh + crack",
    }
    DETAILS = {
        CLASSIC: "A natural outdoor whip crack.",
        SHARP: "A crisp, punchy whip recording.",
        DRY: "A short, direct leather snap.",
        CINEMATIC: "A sweeping whoosh followed by a crack.",
    }


class WhipGesture:
    def __init__(self):
        self.presses = {}

    def press(self, button, time, loading):
        if button in self.presses:
            return False
        self.presses[button] = time
        return not loading

    def release(self, button, time, loading):
        start = self.presses.pop(button, None)
        if start is None:
            return None
        if loading:
            return min(1.0, max(0.0, (time - start) / 0.9))
        return None

    def charge(self, time, loading):
        if not loading or not self.presses:
            return 0.0
        start = min(self.presses.values())
        return min(1.0, max(0.0, (time - start) / 0.9))

    def is_pressed(self, button):
        return button in self.presses

    def cancel(self):
        self.presses.clear()


class CrackTiming:
    def __init__(self):
        self.last_start = float("-inf")

    def next_start(self, now):
        start = max(now + 0.006, self.last_start + 0.095)
        self.last_start = start
        return start


class WhipSimulation:
    def __init__(self):
        self.particles = []
        self.anchor = Point()
        self.flash = 0.0
        self.load_amount = 0.0
        self.handle_angle = REST_ANGLE
        self.handle_angular_velocity = 0.0
        self.wave = -1.0
        self.wave_strength = 0.0
        self.release_bend = 0.0
        self.hang_roll = 0.0
        self.cursor_travel = 0.0
        self.initialized = False
        self._pop_armed = False

    def reset(self, point, length):
        self.anchor = Point(point.x, point.y)
        self.handle_angle = REST_ANGLE
        self.handle_angular_velocity = 0.0
        self.wave = -1.0
        self.wave_strength = 0.0
        self.release_bend = 0.0
        self.hang_roll = 0.0
        self.cursor_travel = 0.0
        self._pop_armed = False
        self.particles = []
        for i in range(COUNT):
            dist = i / (COUNT - 1) * length
            p = self._rest_point(point, dist, length)
            self.particles.append(Particle(p))
        self.initialized = True

    def take_pop(self):
        if not self._pop_armed:
            return False
        self._pop_armed = False
        return True

    def _rest_point(self, point, distance, length):
        return self._curve_point(point, distance, length, 0.0, -1.0)

    def _curve_point(self, point, distance, length, bend, extend):
        hx = math.cos(self.handle_angle)
        hy = math.sin(self.handle_angle)
        if distance <= HANDLE_PIXELS:
            return Point(point.x + hx * distance, point.y + hy * distance)
        ferrule = Point(point.x + hx * HANDLE_PIXELS, point.y + hy * HANDLE_PIXELS)
        lash = max(1.0, length - HANDLE_PIXELS)
        s = distance - HANDLE_PIXELS
        if extend < 0 and bend <= 0:
            return self._hang_point(ferrule, s, lash)
        if extend < 0:
            return self._load_point(ferrule, s, lash, bend)
        return self._crack_point(ferrule, s, lash, bend, extend)

    def _crack_point(self, ferrule, s, lash, bend, extend):
        if bend > 0.02:
            drape = self._load_point(ferrule, s, lash, bend)
        else:
            drape = self._hang_point(ferrule, s, lash)
        if extend <= 0.001:
            return drape
        thrown = -0.1
        tx, ty = math.cos(thrown), math.sin(thrown)
        nx, ny = -math.sin(thrown), math.cos(thrown)
        if extend >= 1:
            straight = self._aimed(ferrule, s, lash, thrown, 0.32)
            hang = self._hang_point(ferrule, s, lash)
            settle = min(1.0, max(0.0, (extend - 1.08) / 0.36))
            eased = settle * settle * (3 - 2 * settle)
            return Point(
                straight.x * (1 - eased) + hang.x * eased,
                straight.y * (1 - eased) + hang.y * eased,
            )
        loop = extend * 0.94
        half = min(max(0.0, loop - 0.015), max(0.028 * (1 - extend), 0.17 * (1 - extend) ** 1.1))
        if half < 0.01 and extend < 0.72:
            shaped = drape
        elif half < 0.01:
            shaped = self._aimed(ferrule, s, lash, thrown, 0.32)
        else:
            radius = max(10.0, (2 * half * lash) / math.pi)
            straight_len = max(0.0, (loop - half) * lash)
            loop_arc = math.pi * radius
            origin = self._aimed(ferrule, straight_len, lash, thrown, 0.32)
            if s <= straight_len:
                shaped = self._aimed(ferrule, s, lash, thrown, 0.32)
            elif s <= straight_len + loop_arc:
                theta = (s - straight_len) / radius
                cx = origin.x + nx * radius
                cy = origin.y + ny * radius
                shaped = Point(
                    cx - nx * radius * math.cos(theta) + tx * radius * math.sin(theta),
                    cy - ny * radius * math.cos(theta) + ty * radius * math.sin(theta),
                )
            else:
                ret = s - straight_len - loop_arc
                free = min(radius * 0.7, max(0.0, lash - straight_len - loop_arc))
                hinge = Point(
                    origin.x + nx * 2 * radius - tx * min(ret, free),
                    origin.y + ny * 2 * radius - ty * min(ret, free),
                )
                if ret <= free:
                    shaped = hinge
                else:
                    remain = max(1.0, lash - straight_len - loop_arc - free)
                    shaped = self._hang_from(hinge, ret - free, remain, bend, thrown + math.pi)
        t = min(1.0, extend / 0.34)
        e = t * t * (3 - 2 * t)
        return Point(drape.x * (1 - e) + shaped.x * e, drape.y * (1 - e) + shaped.y * e)

    def _drape_point(self, ferrule, s, lash, side_left):
        down = -math.pi / 2
        target = down + 2 * math.pi if side_left else down
        delta = target - self.handle_angle
        span = min(lash * 0.38, max(52.0, abs(delta) * 40))
        x, y = ferrule.x, ferrule.y
        walked = 0.0
        while walked < s:
            step = min(3.0, s - walked)
            u = min(1.0, walked / span)
            eased = u * u * (3 - 2 * u)
            angle = self.handle_angle + delta * eased
            x += math.cos(angle) * step
            y += math.sin(angle) * step
            walked += step
        return Point(x, y)

    def _load_point(self, ferrule, s, lash, bend):
        right = self._drape_point(ferrule, s, lash, False)
        left = self._drape_point(ferrule, s, lash, True)
        t = self.hang_roll
        eased = t * t * (3 - 2 * t)
        return Point(right.x * (1 - eased) + left.x * eased, right.y * (1 - eased) + left.y * eased)

    def _hang_point(self, ferrule, s, lash):
        return self._drape_point(ferrule, s, lash, self.handle_angle > math.pi / 2)

    def _aimed(self, ferrule, s, lash, toward, span_fraction):
        span = max(72.0, lash * span_fraction)
        x, y = ferrule.x, ferrule.y
        walked = 0.0
        while walked < s:
            step = min(3.0, s - walked)
            along = min(1.0, walked / span)
            eased = along * along * (3 - 2 * along)
            angle = self.handle_angle + (toward - self.handle_angle) * eased
            tip = min(1.0, walked / lash)
            if tip > 0.8:
                sag = ((tip - 0.8) / 0.2) ** 2
                angle += (-math.pi / 2 + 0.2 - angle) * sag * 0.28
            x += math.cos(angle) * step
            y += math.sin(angle) * step
            walked += step
        return Point(x, y)

    def _hang_from(self, origin, s, length, bend, start_angle):
        down = -math.pi / 2 - 0.16 * bend
        target = down
        while target < start_angle:
            target += 2 * math.pi
        span = max(56.0, length * 0.34)
        x, y = origin.x, origin.y
        walked = 0.0
        while walked < s:
            step = min(3.0, s - walked)
            u = min(1.0, walked / span)
            eased = u * u * (3 - 2 * u)
            angle = start_angle + (target - start_angle) * eased
            x += math.cos(angle) * step
            y += math.sin(angle) * step
            walked += step
        return Point(x, y)

    def crack(self, strength=1.0):
        if not self.initialized:
            return
        self.flash = 0.0
        self.release_bend = self.load_amount
        self.load_amount = 0.0
        self.wave = 0.0
        self.wave_strength = strength
        self._pop_armed = False
        self.handle_angular_velocity = -0.55 * strength

    def _handle_end(self, spacing):
        for i in range(len(self.particles)):
            if spacing * i > HANDLE_PIXELS:
                return i
        return 1

    def _follow(self, point, length, spacing, bend, extend, rate):
        handle_end = self._handle_end(spacing)
        free = max(1.0, float(len(self.particles) - handle_end))
        for i in range(handle_end, len(self.particles)):
            t = (i - handle_end) / free
            target = self._curve_point(point, spacing * i, length, bend, extend)
            follow = rate * (1 - 0.12 * t)
            self.particles[i].p.x += (target.x - self.particles[i].p.x) * follow
            self.particles[i].p.y += (target.y - self.particles[i].p.y) * follow
            self.particles[i].previous = self.particles[i].p.copy()

    def _trail(self, point, length, spacing, travel):
        handle_end = self._handle_end(spacing)
        free = max(1.0, float(len(self.particles) - handle_end))
        moving = min(1.0, travel)
        for i in range(handle_end, len(self.particles)):
            t = (i - handle_end) / free
            vx = self.particles[i].p.x - self.particles[i].previous.x
            vy = self.particles[i].p.y - self.particles[i].previous.y
            self.particles[i].previous = self.particles[i].p.copy()
            damp = 0.55 + 0.3 * moving
            self.particles[i].p.x += vx * damp
            self.particles[i].p.y += vy * damp
            target = self._curve_point(point, spacing * i, length, 0.0, -1.0)
            pull = (0.04 + 0.12 * (1 - moving)) * (1 - 0.82 * t)
            self.particles[i].p.x += (target.x - self.particles[i].p.x) * pull
            self.particles[i].p.y += (target.y - self.particles[i].p.y) * pull

    def _pin_handle(self, point, spacing):
        hx = math.cos(self.handle_angle)
        hy = math.sin(self.handle_angle)
        for i in range(len(self.particles)):
            dist = spacing * i
            if dist > HANDLE_PIXELS:
                break
            self.particles[i].p = Point(point.x + hx * dist, point.y + hy * dist)
            self.particles[i].previous = self.particles[i].p.copy()

    def step(self, point, length, charge=0.0):
        if not self.initialized or math.hypot(point.x - self.anchor.x, point.y - self.anchor.y) > 1100:
            self.reset(point, length)
        moved = math.hypot(point.x - self.anchor.x, point.y - self.anchor.y)
        self.cursor_travel += (min(1.0, moved / 12.0) - self.cursor_travel) * 0.28
        self.anchor = Point(point.x, point.y)
        self.load_amount += (charge - self.load_amount) * 0.18
        rest = REST_ANGLE
        spacing = length / (COUNT - 1)
        bend = 0.0
        extend = -1.0
        rate = 0.2
        if self.wave >= 0:
            if self.wave >= 1.45:
                self.wave = -1.0
                self.wave_strength = 0.0
                self.release_bend = 0.0
            else:
                phase = self.wave
                flick = min(1.0, phase / 0.22) if phase < 1 else max(0.0, 1 - (phase - 1) / 0.42)
                flick_angle = rest - 0.42 * min(1.2, self.wave_strength) * flick
                depart = min(1.0, max(0.0, (phase - 0.05) / 0.3))
                self.handle_angle += (flick_angle - self.handle_angle) * (0.05 + 0.42 * depart)
                bend = self.release_bend
                extend = phase
                rate = 0.45 if phase < 0.02 else 1.0
                before = self.wave
                if self.wave < 1:
                    self.wave = min(1.0, self.wave + 0.022 + 0.08 * self.wave)
                else:
                    self.wave += 0.04
                if before < 0.92 and self.wave >= 0.92:
                    self._pop_armed = True
                    self.flash = 1.0
        elif charge > 0.02:
            self.handle_angle += ((rest + math.pi / 4 * self.load_amount) - self.handle_angle) * 0.14
            want_roll = 1.0 if self.handle_angle > math.pi / 2 else 0.0
            self.hang_roll += (want_roll - self.hang_roll) * (0.055 if want_roll > self.hang_roll else 0.18)
            bend = self.load_amount
            extend = -1.0
            rate = 0.4
        else:
            self.handle_angle += (rest - self.handle_angle) * 0.12
            if self.handle_angle <= math.pi / 2:
                self.hang_roll = 0.0
        self.handle_angle = rest + min(math.pi / 4, max(-0.75, self.handle_angle - rest))
        posing = self.wave >= 0 or charge > 0.02
        self._pin_handle(point, spacing)
        if posing:
            self._follow(point, length, spacing, bend, extend, rate)
        else:
            self._trail(point, length, spacing, self.cursor_travel)
        self._pin_handle(point, spacing)
        handle_end = self._handle_end(spacing)
        if not posing:
            give = 0.12 + 0.4 * (1 - min(1.0, self.cursor_travel))
            self._pin_handle(point, spacing)
            for i in range(handle_end, len(self.particles)):
                a = self.particles[i - 1].p
                b = self.particles[i].p
                dx = b.x - a.x
                dy = b.y - a.y
                distance = max(0.001, math.hypot(dx, dy))
                slack = distance - spacing
                compress = 0.2 if slack < 0 else 1.0
                limit = 0.85 if distance > spacing * 1.7 else give
                correction = slack / distance * limit * compress
                if i == handle_end:
                    self.particles[i].p.x -= dx * correction
                    self.particles[i].p.y -= dy * correction
                else:
                    self.particles[i - 1].p.x += dx * correction * 0.25
                    self.particles[i - 1].p.y += dy * correction * 0.25
                    self.particles[i].p.x -= dx * correction * 0.75
                    self.particles[i].p.y -= dy * correction * 0.75
        self._pin_handle(point, spacing)
        self.flash = max(0.0, self.flash - 0.07)


def run_golden_script(simulation=None):
    """The same script the macOS --physics-golden flag prints."""
    simulation = simulation or WhipSimulation()
    marks = []

    def dump(tag):
        marks.append((tag, simulation))

    snapshots = []

    def capture(tag):
        snapshots.append(snapshot(tag, simulation))

    for i in range(180):
        t = i / 60.0
        simulation.step(Point(500 + math.sin(t) * 200, 500 + math.cos(t * 2) * 100), 340)
        if i == 40:
            simulation.crack()
        if i in (0, 40, 41, 70, 110, 179):
            capture(f"move-{i}")
    for i in range(240):
        simulation.step(Point(200, 200), 340, 1)
        if i in (30, 239):
            capture(f"load-{i}")
    simulation.crack(strength=1.65)
    capture("release-0")
    for i in range(80):
        simulation.step(Point(200, 200), 340)
        if i in (8, 20, 45, 79):
            capture(f"settle-{i}")
    simulation.step(Point(-1500, 900), 260)
    capture("jump")
    return snapshots


def snapshot(tag, simulation):
    values = [
        simulation.anchor.x,
        simulation.anchor.y,
        simulation.handle_angle,
        simulation.load_amount,
        simulation.wave,
        simulation.flash,
        simulation.hang_roll,
        simulation.wave_strength,
        simulation.release_bend,
        simulation.cursor_travel,
    ]
    for particle in simulation.particles:
        values.append(particle.p.x)
        values.append(particle.p.y)
    return tag, len(simulation.particles), values
