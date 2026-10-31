#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const Whip = require("./whip.js");

const goldenPath = path.join(__dirname, "..", "desktop", "physics-golden.txt");
const lines = fs.readFileSync(goldenPath, "utf8").trim().split("\n");
const snaps = Whip.runGoldenScript();
if (lines.length !== snaps.length) {
  console.error("frame count " + lines.length + " != " + snaps.length);
  process.exit(1);
}
let worst = 0;
lines.forEach((line, index) => {
  const parts = line.split(" ");
  const snap = snaps[index];
  if (parts[0] !== snap[0] || Number(parts[1]) !== snap[1]) {
    console.error("mismatch at " + parts[0]);
    process.exit(1);
  }
  parts.slice(2).forEach((item, i) => {
    worst = Math.max(worst, Math.abs(Number(item) - snap[2][i]));
  });
});
if (worst >= 1e-8) {
  console.error("physics drifted by " + worst);
  process.exit(1);
}

if (process.argv.includes("--strokes")) {
  const sim = new Whip.WhipSimulation();
  for (let i = 0; i < 180; i++) {
    const t = i / 60;
    sim.step(new Whip.Point(500 + Math.sin(t) * 200, 500 + Math.cos(t * 2) * 100), 340);
    if (i === 40) sim.crack();
  }
  for (let i = 0; i < 240; i++) sim.step(new Whip.Point(200, 200), 340, 1);
  const strokes = Whip.whipStrokes(sim, [0.96, 0.47, 0.26], 1, "flared");
  const numbers = [];
  strokes.forEach((stroke) => {
    if (stroke[0] === "line") numbers.push(...stroke.slice(1, 10));
    else if (stroke[0] === "fill" || stroke[0] === "clip") stroke[1].forEach((p) => numbers.push(...p));
    else if (stroke[0] === "arc" || stroke[0] === "dot") numbers.push(...stroke.slice(1));
  });
  process.stdout.write(JSON.stringify(numbers));
} else {
  console.log("PASS: web physics matches macOS within " + worst.toExponential(2));
}
