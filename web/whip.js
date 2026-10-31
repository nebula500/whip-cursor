/* Whip Cursor simulation and leather renderer.
   Web version of the whip. The formulas match the macOS app and desktop/whip_sim.py.
   Coordinates are y-up until paint time. */
(function (root, factory) {
  var api = factory();
  root.WhipCursor = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var COUNT = 40;
  var REST_ANGLE = Math.PI / 3;
  var HANDLE_PIXELS = 46;
  var PI = Math.PI;

  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

  function HandleRadius(shape, distance) {
    var t = clamp(distance / HANDLE_PIXELS, 0, 1);
    if (shape === "straight") return 5.5;
    if (shape === "tapered") return 6.5 - 2.2 * t;
    return 4.4 + 2.7 * Math.pow(1 - t, 3) + 1.3 * Math.pow(t, 6);
  }

  function WhipGesture() {
    this.presses = {};
  }
  WhipGesture.prototype.press = function (button, time, loading) {
    if (Object.prototype.hasOwnProperty.call(this.presses, button)) return false;
    this.presses[button] = time;
    return !loading;
  };
  WhipGesture.prototype.release = function (button, time, loading) {
    if (!Object.prototype.hasOwnProperty.call(this.presses, button)) return null;
    var start = this.presses[button];
    delete this.presses[button];
    return loading ? clamp((time - start) / 0.9, 0, 1) : null;
  };
  WhipGesture.prototype.charge = function (time, loading) {
    var keys = Object.keys(this.presses);
    if (!loading || !keys.length) return 0;
    var start = Math.min.apply(null, keys.map(function (k) { return this.presses[k]; }, this));
    return clamp((time - start) / 0.9, 0, 1);
  };
  WhipGesture.prototype.cancel = function () { this.presses = {}; };

  function CrackTiming() { this.lastStart = -Infinity; }
  CrackTiming.prototype.nextStart = function (now) {
    var start = Math.max(now + 0.006, this.lastStart + 0.095);
    this.lastStart = start;
    return start;
  };

  function Point(x, y) { this.x = x; this.y = y; }
  function Particle(p) { this.p = p; this.previous = new Point(p.x, p.y); }

  function WhipSimulation() {
    this.particles = [];
    this.anchor = new Point(0, 0);
    this.flash = 0;
    this.loadAmount = 0;
    this.handleAngle = REST_ANGLE;
    this.handleAngularVelocity = 0;
    this.wave = -1;
    this.waveStrength = 0;
    this.releaseBend = 0;
    this.hangRoll = 0;
    this.cursorTravel = 0;
    this.initialized = false;
    this.popArmed = false;
  }

  WhipSimulation.prototype.reset = function (point, length) {
    this.anchor = new Point(point.x, point.y);
    this.handleAngle = REST_ANGLE;
    this.handleAngularVelocity = 0;
    this.wave = -1;
    this.waveStrength = 0;
    this.releaseBend = 0;
    this.hangRoll = 0;
    this.cursorTravel = 0;
    this.popArmed = false;
    this.particles = [];
    for (var i = 0; i < COUNT; i++) {
      var dist = i / (COUNT - 1) * length;
      var p = this.restPoint(point, dist, length);
      this.particles.push(new Particle(p));
    }
    this.initialized = true;
  };
  WhipSimulation.prototype.takePop = function () {
    if (!this.popArmed) return false;
    this.popArmed = false;
    return true;
  };
  WhipSimulation.prototype.restPoint = function (point, distance, length) {
    return this.curvePoint(point, distance, length, 0, -1);
  };
  WhipSimulation.prototype.curvePoint = function (point, distance, length, bend, extend) {
    var hx = Math.cos(this.handleAngle), hy = Math.sin(this.handleAngle);
    if (distance <= HANDLE_PIXELS) return new Point(point.x + hx * distance, point.y + hy * distance);
    var ferrule = new Point(point.x + hx * HANDLE_PIXELS, point.y + hy * HANDLE_PIXELS);
    var lash = Math.max(1, length - HANDLE_PIXELS);
    var s = distance - HANDLE_PIXELS;
    if (extend < 0 && bend <= 0) return this.hangPoint(ferrule, s, lash);
    if (extend < 0) return this.loadPoint(ferrule, s, lash, bend);
    return this.crackPoint(ferrule, s, lash, bend, extend);
  };
  WhipSimulation.prototype.crackPoint = function (ferrule, s, lash, bend, extend) {
    var drape = bend > 0.02 ? this.loadPoint(ferrule, s, lash, bend) : this.hangPoint(ferrule, s, lash);
    if (extend <= 0.001) return drape;
    var thrown = -0.1;
    var tx = Math.cos(thrown), ty = Math.sin(thrown);
    var nx = -Math.sin(thrown), ny = Math.cos(thrown);
    if (extend >= 1) {
      var straight = this.aimed(ferrule, s, lash, thrown, 0.32);
      var hang = this.hangPoint(ferrule, s, lash);
      var settle = clamp((extend - 1.08) / 0.36, 0, 1);
      var eased = settle * settle * (3 - 2 * settle);
      return new Point(straight.x * (1 - eased) + hang.x * eased, straight.y * (1 - eased) + hang.y * eased);
    }
    var loop = extend * 0.94;
    var half = Math.min(Math.max(0, loop - 0.015), Math.max(0.028 * (1 - extend), 0.17 * Math.pow(1 - extend, 1.1)));
    var shaped;
    if (half < 0.01 && extend < 0.72) shaped = drape;
    else if (half < 0.01) shaped = this.aimed(ferrule, s, lash, thrown, 0.32);
    else {
      var R = Math.max(10, (2 * half * lash) / PI);
      var straightLen = Math.max(0, (loop - half) * lash);
      var loopArc = PI * R;
      var origin = this.aimed(ferrule, straightLen, lash, thrown, 0.32);
      if (s <= straightLen) shaped = this.aimed(ferrule, s, lash, thrown, 0.32);
      else if (s <= straightLen + loopArc) {
        var theta = (s - straightLen) / R;
        var cx = origin.x + nx * R, cy = origin.y + ny * R;
        shaped = new Point(
          cx - nx * R * Math.cos(theta) + tx * R * Math.sin(theta),
          cy - ny * R * Math.cos(theta) + ty * R * Math.sin(theta)
        );
      } else {
        var ret = s - straightLen - loopArc;
        var free = Math.min(R * 0.7, Math.max(0, lash - straightLen - loopArc));
        var hinge = new Point(origin.x + nx * 2 * R - tx * Math.min(ret, free), origin.y + ny * 2 * R - ty * Math.min(ret, free));
        if (ret <= free) shaped = hinge;
        else shaped = this.hangFrom(hinge, ret - free, Math.max(1, lash - straightLen - loopArc - free), bend, thrown + PI);
      }
    }
    var t = Math.min(1, extend / 0.34);
    var e = t * t * (3 - 2 * t);
    return new Point(drape.x * (1 - e) + shaped.x * e, drape.y * (1 - e) + shaped.y * e);
  };
  WhipSimulation.prototype.drapePoint = function (ferrule, s, lash, sideLeft) {
    var down = -PI / 2;
    var target = sideLeft ? down + 2 * PI : down;
    var delta = target - this.handleAngle;
    var span = Math.min(lash * 0.38, Math.max(52, Math.abs(delta) * 40));
    var x = ferrule.x, y = ferrule.y, walked = 0;
    while (walked < s) {
      var step = Math.min(3, s - walked);
      var u = Math.min(1, walked / span);
      var eased = u * u * (3 - 2 * u);
      var angle = this.handleAngle + delta * eased;
      x += Math.cos(angle) * step;
      y += Math.sin(angle) * step;
      walked += step;
    }
    return new Point(x, y);
  };
  WhipSimulation.prototype.loadPoint = function (ferrule, s, lash) {
    var right = this.drapePoint(ferrule, s, lash, false);
    var left = this.drapePoint(ferrule, s, lash, true);
    var t = this.hangRoll;
    var eased = t * t * (3 - 2 * t);
    return new Point(right.x * (1 - eased) + left.x * eased, right.y * (1 - eased) + left.y * eased);
  };
  WhipSimulation.prototype.hangPoint = function (ferrule, s, lash) {
    return this.drapePoint(ferrule, s, lash, this.handleAngle > PI / 2);
  };
  WhipSimulation.prototype.aimed = function (ferrule, s, lash, toward, spanFraction) {
    var span = Math.max(72, lash * spanFraction);
    var x = ferrule.x, y = ferrule.y, walked = 0;
    while (walked < s) {
      var step = Math.min(3, s - walked);
      var along = Math.min(1, walked / span);
      var eased = along * along * (3 - 2 * along);
      var angle = this.handleAngle + (toward - this.handleAngle) * eased;
      var tip = Math.min(1, walked / lash);
      if (tip > 0.8) {
        var sag = Math.pow((tip - 0.8) / 0.2, 2);
        angle += (-PI / 2 + 0.2 - angle) * sag * 0.28;
      }
      x += Math.cos(angle) * step;
      y += Math.sin(angle) * step;
      walked += step;
    }
    return new Point(x, y);
  };
  WhipSimulation.prototype.hangFrom = function (origin, s, length, bend, startAngle) {
    var down = -PI / 2 - 0.16 * bend;
    var target = down;
    while (target < startAngle) target += 2 * PI;
    var span = Math.max(56, length * 0.34);
    var x = origin.x, y = origin.y, walked = 0;
    while (walked < s) {
      var step = Math.min(3, s - walked);
      var u = Math.min(1, walked / span);
      var eased = u * u * (3 - 2 * u);
      var angle = startAngle + (target - startAngle) * eased;
      x += Math.cos(angle) * step;
      y += Math.sin(angle) * step;
      walked += step;
    }
    return new Point(x, y);
  };
  WhipSimulation.prototype.crack = function (strength) {
    if (strength === undefined) strength = 1;
    if (!this.initialized) return;
    this.flash = 0;
    this.releaseBend = this.loadAmount;
    this.loadAmount = 0;
    this.wave = 0;
    this.waveStrength = strength;
    this.popArmed = false;
    this.handleAngularVelocity = -0.55 * strength;
  };
  WhipSimulation.prototype.handleEnd = function (spacing) {
    for (var i = 0; i < this.particles.length; i++) if (spacing * i > HANDLE_PIXELS) return i;
    return 1;
  };
  WhipSimulation.prototype.follow = function (point, length, spacing, bend, extend, rate) {
    var handleEnd = this.handleEnd(spacing);
    var free = Math.max(1, this.particles.length - handleEnd);
    for (var i = handleEnd; i < this.particles.length; i++) {
      var t = (i - handleEnd) / free;
      var target = this.curvePoint(point, spacing * i, length, bend, extend);
      var follow = rate * (1 - 0.12 * t);
      this.particles[i].p.x += (target.x - this.particles[i].p.x) * follow;
      this.particles[i].p.y += (target.y - this.particles[i].p.y) * follow;
      this.particles[i].previous = new Point(this.particles[i].p.x, this.particles[i].p.y);
    }
  };
  WhipSimulation.prototype.trail = function (point, length, spacing, travel) {
    var handleEnd = this.handleEnd(spacing);
    var free = Math.max(1, this.particles.length - handleEnd);
    var moving = Math.min(1, travel);
    for (var i = handleEnd; i < this.particles.length; i++) {
      var t = (i - handleEnd) / free;
      var vx = this.particles[i].p.x - this.particles[i].previous.x;
      var vy = this.particles[i].p.y - this.particles[i].previous.y;
      this.particles[i].previous = new Point(this.particles[i].p.x, this.particles[i].p.y);
      var damp = 0.55 + 0.3 * moving;
      this.particles[i].p.x += vx * damp;
      this.particles[i].p.y += vy * damp;
      var target = this.curvePoint(point, spacing * i, length, 0, -1);
      var pull = (0.04 + 0.12 * (1 - moving)) * (1 - 0.82 * t);
      this.particles[i].p.x += (target.x - this.particles[i].p.x) * pull;
      this.particles[i].p.y += (target.y - this.particles[i].p.y) * pull;
    }
  };
  WhipSimulation.prototype.pinHandle = function (point, spacing) {
    var hx = Math.cos(this.handleAngle), hy = Math.sin(this.handleAngle);
    for (var i = 0; i < this.particles.length; i++) {
      var dist = spacing * i;
      if (dist > HANDLE_PIXELS) break;
      this.particles[i].p = new Point(point.x + hx * dist, point.y + hy * dist);
      this.particles[i].previous = new Point(this.particles[i].p.x, this.particles[i].p.y);
    }
  };
  WhipSimulation.prototype.step = function (point, length, charge) {
    if (charge === undefined) charge = 0;
    if (!this.initialized || Math.hypot(point.x - this.anchor.x, point.y - this.anchor.y) > 1100) this.reset(point, length);
    var moved = Math.hypot(point.x - this.anchor.x, point.y - this.anchor.y);
    this.cursorTravel += (Math.min(1, moved / 12) - this.cursorTravel) * 0.28;
    this.anchor = new Point(point.x, point.y);
    this.loadAmount += (charge - this.loadAmount) * 0.18;
    var rest = REST_ANGLE;
    var spacing = length / (COUNT - 1);
    var bend = 0, extend = -1, rate = 0.2;
    if (this.wave >= 0) {
      if (this.wave >= 1.45) {
        this.wave = -1;
        this.waveStrength = 0;
        this.releaseBend = 0;
      } else {
        var phase = this.wave;
        var flick = phase < 1 ? Math.min(1, phase / 0.22) : Math.max(0, 1 - (phase - 1) / 0.42);
        var flickAngle = rest - 0.42 * Math.min(1.2, this.waveStrength) * flick;
        var depart = clamp((phase - 0.05) / 0.3, 0, 1);
        this.handleAngle += (flickAngle - this.handleAngle) * (0.05 + 0.42 * depart);
        bend = this.releaseBend;
        extend = phase;
        rate = phase < 0.02 ? 0.45 : 1;
        var before = this.wave;
        if (this.wave < 1) this.wave = Math.min(1, this.wave + 0.022 + 0.08 * this.wave);
        else this.wave += 0.04;
        if (before < 0.92 && this.wave >= 0.92) {
          this.popArmed = true;
          this.flash = 1;
        }
      }
    } else if (charge > 0.02) {
      this.handleAngle += ((rest + PI / 4 * this.loadAmount) - this.handleAngle) * 0.14;
      var wantRoll = this.handleAngle > PI / 2 ? 1 : 0;
      this.hangRoll += (wantRoll - this.hangRoll) * (wantRoll > this.hangRoll ? 0.055 : 0.18);
      bend = this.loadAmount;
      extend = -1;
      rate = 0.4;
    } else {
      this.handleAngle += (rest - this.handleAngle) * 0.12;
      if (this.handleAngle <= PI / 2) this.hangRoll = 0;
    }
    this.handleAngle = rest + Math.min(PI / 4, Math.max(-0.75, this.handleAngle - rest));
    var posing = this.wave >= 0 || charge > 0.02;
    this.pinHandle(point, spacing);
    if (posing) this.follow(point, length, spacing, bend, extend, rate);
    else this.trail(point, length, spacing, this.cursorTravel);
    this.pinHandle(point, spacing);
    var handleEnd = this.handleEnd(spacing);
    if (!posing) {
      var give = 0.12 + 0.4 * (1 - Math.min(1, this.cursorTravel));
      this.pinHandle(point, spacing);
      for (var i = handleEnd; i < this.particles.length; i++) {
        var a = this.particles[i - 1].p, b = this.particles[i].p;
        var dx = b.x - a.x, dy = b.y - a.y;
        var distance = Math.max(0.001, Math.hypot(dx, dy));
        var slack = distance - spacing;
        var compress = slack < 0 ? 0.2 : 1;
        var limit = distance > spacing * 1.7 ? 0.85 : give;
        var correction = slack / distance * limit * compress;
        if (i === handleEnd) {
          this.particles[i].p.x -= dx * correction;
          this.particles[i].p.y -= dy * correction;
        } else {
          this.particles[i - 1].p.x += dx * correction * 0.25;
          this.particles[i - 1].p.y += dy * correction * 0.25;
          this.particles[i].p.x -= dx * correction * 0.75;
          this.particles[i].p.y -= dy * correction * 0.75;
        }
      }
    }
    this.pinHandle(point, spacing);
    this.flash = Math.max(0, this.flash - 0.07);
  };

  function runGoldenScript() {
    var simulation = new WhipSimulation();
    var snaps = [];
    function capture(tag) {
      var values = [
        simulation.anchor.x, simulation.anchor.y, simulation.handleAngle, simulation.loadAmount,
        simulation.wave, simulation.flash, simulation.hangRoll, simulation.waveStrength,
        simulation.releaseBend, simulation.cursorTravel
      ];
      for (var i = 0; i < simulation.particles.length; i++) {
        values.push(simulation.particles[i].p.x, simulation.particles[i].p.y);
      }
      snaps.push([tag, simulation.particles.length, values]);
    }
    for (var i = 0; i < 180; i++) {
      var t = i / 60;
      simulation.step(new Point(500 + Math.sin(t) * 200, 500 + Math.cos(t * 2) * 100), 340);
      if (i === 40) simulation.crack();
      if (i === 0 || i === 40 || i === 41 || i === 70 || i === 110 || i === 179) capture("move-" + i);
    }
    for (var j = 0; j < 240; j++) {
      simulation.step(new Point(200, 200), 340, 1);
      if (j === 30 || j === 239) capture("load-" + j);
    }
    simulation.crack(1.65);
    capture("release-0");
    for (var k = 0; k < 80; k++) {
      simulation.step(new Point(200, 200), 340);
      if (k === 8 || k === 20 || k === 45 || k === 79) capture("settle-" + k);
    }
    simulation.step(new Point(-1500, 900), 260);
    capture("jump");
    return snaps;
  }

  function blend(color, fraction, other) {
    return [
      color[0] * (1 - fraction) + other[0] * fraction,
      color[1] * (1 - fraction) + other[1] * fraction,
      color[2] * (1 - fraction) + other[2] * fraction
    ];
  }
  function cubic(p0, p1, p2, p3, steps) {
    var points = [];
    for (var i = 1; i <= steps; i++) {
      var t = i / steps, u = 1 - t;
      points.push([
        u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
        u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
      ]);
    }
    return points;
  }

  function whipStrokes(simulation, color, thickness, handleShape) {
    if (!simulation.initialized || simulation.particles.length < 2) return [];
    if (thickness === undefined) thickness = 1;
    if (!handleShape) handleShape = "straight";
    var black = [0, 0, 0], white = [1, 1, 1];
    var hx = Math.cos(simulation.handleAngle), hy = Math.sin(simulation.handleAngle);
    var butt = [simulation.particles[0].p.x, simulation.particles[0].p.y];
    var ferrule = [butt[0] + hx * HANDLE_PIXELS, butt[1] + hy * HANDLE_PIXELS];
    var control = [ferrule];
    var chain = 0, previous = butt.slice(), passed = false;
    for (var n = 1; n < simulation.particles.length; n++) {
      var current = [simulation.particles[n].p.x, simulation.particles[n].p.y];
      chain += Math.hypot(current[0] - previous[0], current[1] - previous[1]);
      previous = current;
      if (chain < HANDLE_PIXELS) continue;
      if (!passed) { passed = true; continue; }
      control.push(current);
    }
    if (control.length < 2) return [];
    var points = [];
    for (var i = 0; i < control.length - 1; i++) {
      var a = control[i], b = control[i + 1];
      for (var k = 0; k < 3; k++) {
        var t = k / 3;
        points.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      }
    }
    points.push(control[control.length - 1]);
    function width(tt) {
      return HandleRadius(handleShape, HANDLE_PIXELS) * 1.15 * Math.pow(Math.max(0, 1 - tt), 1.15) + 0.5;
    }
    var distances = [0];
    for (var d = 1; d < points.length; d++) {
      distances.push(distances[distances.length - 1] + Math.hypot(points[d][0] - points[d - 1][0], points[d][1] - points[d - 1][1]));
    }
    var total = Math.max(1, distances[distances.length - 1]);
    var strokes = [];
    function line(p, q, w, ink) {
      strokes.push(["line", p[0], p[1], q[0], q[1], w * thickness, ink[0], ink[1], ink[2], ink.length === 4 ? ink[3] : 1]);
    }
    for (var s = 1; s < points.length; s++) {
      var pa = points[s - 1], pb = points[s];
      var tt = distances[s] / total;
      var w = width(tt);
      var dist = Math.max(0.001, Math.hypot(pb[0] - pa[0], pb[1] - pa[1]));
      var normal = [-(pb[1] - pa[1]) / dist, (pb[0] - pa[0]) / dist];
      line(pa, pb, w + 1, blend(color, 0.72, black).concat([0.9]));
      line(pa, pb, w, blend(color, 0.24, black).concat([1]));
      var shift = w * 0.20 * thickness;
      line(
        [pa[0] + normal[0] * shift, pa[1] + normal[1] * shift],
        [pb[0] + normal[0] * shift, pb[1] + normal[1] * shift],
        Math.max(0.3, w * 0.38),
        blend(color, 0.22, white).concat([1])
      );
    }
    var ridge = 4, segment = 1;
    while (ridge < total * 0.88 && segment < distances.length) {
      while (segment < distances.length - 1 && distances[segment] < ridge) segment++;
      if (segment >= distances.length) break;
      var ra = points[segment - 1], rb = points[segment];
      var span = Math.max(0.001, distances[segment] - distances[segment - 1]);
      var f = (ridge - distances[segment - 1]) / span;
      var center = [ra[0] + (rb[0] - ra[0]) * f, ra[1] + (rb[1] - ra[1]) * f];
      var dx = (rb[0] - ra[0]) / span, dy = (rb[1] - ra[1]) / span;
      var rw = width(ridge / total) * 0.46 * thickness;
      function local(along, across) {
        return [center[0] + dx * along * thickness - dy * across, center[1] + dy * along * thickness + dx * across];
      }
      line(local(-1.25, -rw), local(1.1, 0), 0.85, blend(color, 0.7, black).concat([0.85]));
      line(local(1.1, 0), local(-1.25, rw), 0.85, blend(color, 0.7, black).concat([0.85]));
      line(local(-0.65, -rw * 0.85), local(1.65, 0), 0.45, blend(color, 0.4, white).concat([0.8]));
      line(local(1.65, 0), local(-0.65, rw * 0.85), 0.45, blend(color, 0.23, white).concat([0.7]));
      ridge += Math.max(2.2, rw * 0.95);
    }
    function grip(along, across) {
      if (across === undefined) across = 0;
      return [butt[0] + hx * along - hy * across * thickness, butt[1] + hy * along + hx * across * thickness];
    }
    var polygon = [grip(0, -HandleRadius(handleShape, 0))];
    for (var gr = 1; gr <= HANDLE_PIXELS + 1e-6; gr += 1) polygon.push(grip(gr, -HandleRadius(handleShape, gr)));
    var tipRadius = HandleRadius(handleShape, HANDLE_PIXELS);
    polygon = polygon.concat(cubic(polygon[polygon.length - 1], grip(HANDLE_PIXELS + 3, -tipRadius), grip(HANDLE_PIXELS + 3, tipRadius), grip(HANDLE_PIXELS, tipRadius), 6));
    for (var gr2 = HANDLE_PIXELS - 1; gr2 >= -1e-6; gr2 -= 1) polygon.push(grip(gr2, HandleRadius(handleShape, gr2)));
    var buttRadius = HandleRadius(handleShape, 0);
    polygon = polygon.concat(cubic(polygon[polygon.length - 1], grip(-3, buttRadius), grip(-3, -buttRadius), grip(0, -buttRadius), 6));
    var fill = blend(color, 0.72, black).concat([1]);
    strokes.push(["fill", polygon, fill[0], fill[1], fill[2], fill[3]]);
    strokes.push(["clip", polygon]);
    line(grip(0, 1), grip(HANDLE_PIXELS, 1), 7.8, blend(color, 0.45, black).concat([1]));
    line(grip(1, 2.6), grip(HANDLE_PIXELS, 2.6), 1.2, blend(color, 0.12, white).concat([0.75]));
    for (var wr = 3; wr <= HANDLE_PIXELS - 2 + 1e-6; wr += 3) {
      var radius = HandleRadius(handleShape, wr) * 0.88;
      line(grip(wr - 1, -radius), grip(wr + 1.5, radius), 1, blend(color, 0.85, black).concat([1]));
      line(grip(wr - 0.3, -radius), grip(wr + 2.2, radius), 0.55, blend(color, 0.14, white).concat([1]));
    }
    strokes.push(["unclip"]);
    [0, HANDLE_PIXELS].forEach(function (end) {
      var radius = HandleRadius(handleShape, end) * 0.9;
      line(grip(end, -radius), grip(end, radius), 2.1, [0.15, 0.15, 0.15, 1]);
      line(grip(end + 0.5, -radius), grip(end + 0.5, radius), 0.7, [0.55, 0.55, 0.55, 1]);
    });
    if (simulation.loadAmount > 0.02) {
      strokes.push(["arc", butt[0], butt[1], 14 + thickness * 3, 90, 90 + 360 * simulation.loadAmount, 1.8, color[0], color[1], color[2], 0.85]);
    }
    strokes.push(["dot", butt[0], butt[1], 1.3, 1, 1, 1, 0.8]);
    if (simulation.flash > 0) {
      var tip = points[points.length - 1];
      var flash = simulation.flash;
      for (var ray = 0; ray < 7; ray++) {
        var angle = ray * 2 * PI / 7;
        var inner = 6 + (1 - flash) * 15;
        var outer = inner + flash * 16;
        line(
          [tip[0] + Math.cos(angle) * inner, tip[1] + Math.sin(angle) * inner],
          [tip[0] + Math.cos(angle) * outer, tip[1] + Math.sin(angle) * outer],
          1.8,
          color.concat([flash])
        );
      }
    }
    return strokes;
  }

  function paintCanvas(ctx, strokes, mapX, mapY) {
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    var clipped = false;
    function rgba(r, g, b, a) {
      return "rgba(" + Math.round(r * 255) + "," + Math.round(g * 255) + "," + Math.round(b * 255) + "," + (a === undefined ? 1 : a) + ")";
    }
    for (var i = 0; i < strokes.length; i++) {
      var s = strokes[i];
      if (s[0] === "clip") {
        ctx.save();
        ctx.beginPath();
        s[1].forEach(function (p, index) {
          var x = mapX(p[0]), y = mapY(p[1]);
          if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.closePath();
        ctx.clip();
        clipped = true;
        continue;
      }
      if (s[0] === "unclip") {
        if (clipped) ctx.restore();
        clipped = false;
        continue;
      }
      if (s[0] === "fill") {
        ctx.beginPath();
        s[1].forEach(function (p, index) {
          var x = mapX(p[0]), y = mapY(p[1]);
          if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.closePath();
        ctx.fillStyle = rgba(s[2], s[3], s[4], s[5]);
        ctx.fill();
        continue;
      }
      if (s[0] === "line") {
        ctx.beginPath();
        ctx.moveTo(mapX(s[1]), mapY(s[2]));
        ctx.lineTo(mapX(s[3]), mapY(s[4]));
        ctx.lineWidth = Math.max(0.4, s[5]);
        ctx.strokeStyle = rgba(s[6], s[7], s[8], s[9]);
        ctx.stroke();
        continue;
      }
      if (s[0] === "dot") {
        ctx.beginPath();
        ctx.arc(mapX(s[1]), mapY(s[2]), s[3], 0, PI * 2);
        ctx.fillStyle = rgba(s[4], s[5], s[6], s[7]);
        ctx.fill();
        continue;
      }
      if (s[0] === "arc") {
        var start = -s[4] * PI / 180;
        var end = -s[5] * PI / 180;
        ctx.beginPath();
        ctx.arc(mapX(s[1]), mapY(s[2]), s[3], start, end, true);
        ctx.lineWidth = Math.max(0.6, s[6]);
        ctx.strokeStyle = rgba(s[7], s[8], s[9], s[10]);
        ctx.stroke();
      }
    }
    if (clipped) ctx.restore();
  }

  return {
    COUNT: COUNT,
    REST_ANGLE: REST_ANGLE,
    HANDLE_PIXELS: HANDLE_PIXELS,
    LENGTH_MIN: 180,
    LENGTH_MAX: 540,
    LENGTH_DEFAULT: 340,
    WhipSimulation: WhipSimulation,
    WhipGesture: WhipGesture,
    CrackTiming: CrackTiming,
    Point: Point,
    HandleRadius: HandleRadius,
    runGoldenScript: runGoldenScript,
    whipStrokes: whipStrokes,
    paintCanvas: paintCanvas,
    SWATCHES: [
      ["Ember", [0.96, 0.47, 0.26]],
      ["Mint", [0.42, 0.89, 0.72]],
      ["Lavender", [0.68, 0.58, 1]],
      ["Ice", [0.40, 0.76, 1]],
      ["Rose", [1, 0.48, 0.66]],
      ["Pearl", [0.94, 0.94, 0.88]]
    ]
  };
});
