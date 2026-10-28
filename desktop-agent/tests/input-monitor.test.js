const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { createInputMonitor, MAX_INTERVAL_COUNT } = require("../electron/input-monitor");

function fixture(options = {}) {
  const hook = new EventEmitter();
  hook.starts = hook.stops = 0;
  hook.start = () => { hook.starts++; };
  hook.stop = () => { hook.stops++; };
  const monitor = createInputMonitor({ loadHook: () => hook, ...options });
  return { hook, monitor };
}

test("does not load the native input hook before a work session", () => {
  let loads = 0;
  const monitor = createInputMonitor({ loadHook: () => { loads++; throw Error(); } });
  monitor.stop();
  assert.equal(loads, 0);
  assert.equal(monitor.status().active, false);
});

test("counts key-down and mouse-down once, without counting key-up or duplicate click events", () => {
  const { hook, monitor } = fixture();
  monitor.start();
  hook.emit("keydown", { keycode: 30 });
  hook.emit("keyup", { keycode: 30 });
  hook.emit("mousedown", { button: 1 });
  hook.emit("mouseup", { button: 1 });
  hook.emit("click", { button: 1 });
  assert.deepEqual(monitor.drain(), { keyboard_count: 1, mouse_count: 1 });
  monitor.stop();
});

test("interval drains preserve session totals and retain following events for the next interval", () => {
  const { hook, monitor } = fixture();
  monitor.start();
  for (let i = 0; i < 37; i++) hook.emit("keydown");
  assert.equal(monitor.drain().keyboard_count, 37);
  hook.emit("keydown");
  assert.equal(monitor.drain().keyboard_count, 1);
  assert.equal(monitor.status().session_keyboard_count, 38);
  assert.equal(monitor.drain().keyboard_count, 0);
  monitor.stop();
});

test("raw characters, keycodes and mouse coordinates are never read or exposed", () => {
  const { hook, monitor } = fixture();
  const raw = new Proxy({}, { get() { throw new Error("Raw event payload was accessed"); } });
  monitor.start();
  hook.emit("keydown", raw);
  hook.emit("mousedown", raw);
  hook.emit("mousemove", raw);
  hook.emit("wheel", raw);
  assert.deepEqual(Object.keys(monitor.drain()).sort(), ["keyboard_count", "mouse_count"]);
  assert.equal(JSON.stringify(monitor.status()).includes("keycode"), false);
  monitor.stop();
});

test("mouse movement and scrolling update activity but do not inflate mouse clicks", () => {
  let activity = 0;
  const { hook, monitor } = fixture({ now: () => 42, onActivity: () => { activity++; } });
  monitor.start();
  hook.emit("mousemove");
  hook.emit("wheel");
  assert.equal(activity, 2);
  assert.equal(monitor.status().last_input_at, 42);
  assert.equal(monitor.drain().mouse_count, 0);
  monitor.stop();
});

test("stop removes listeners and rejects callbacks already queued before punch-out", () => {
  const { hook, monitor } = fixture();
  monitor.start();
  hook.emit("keydown");
  const queued = hook.listeners("keydown")[0];
  monitor.stop();
  queued();
  hook.emit("keydown");
  assert.equal(hook.listenerCount("keydown"), 0);
  assert.equal(monitor.drain().keyboard_count, 1);
  assert.equal(hook.stops, 1);
});

test("pause/resume retains totals and repeated start does not add duplicate listeners", () => {
  const { hook, monitor } = fixture();
  monitor.start();
  monitor.start();
  hook.emit("keydown");
  monitor.pause();
  hook.emit("keydown");
  assert.equal(monitor.status().state, "paused");
  monitor.start();
  hook.emit("keydown");
  assert.equal(hook.listenerCount("keydown"), 1);
  assert.equal(hook.starts, 2);
  assert.equal(monitor.status().session_keyboard_count, 2);
  monitor.stop();
});

test("a new session resets both pending counts and session totals", () => {
  const { hook, monitor } = fixture();
  monitor.start(); hook.emit("keydown"); hook.emit("mousedown");
  monitor.reset(); monitor.start();
  assert.equal(monitor.status().session_keyboard_count, 0);
  assert.equal(monitor.status().session_mouse_count, 0);
  assert.deepEqual(monitor.drain(), { keyboard_count: 0, mouse_count: 0 });
  monitor.stop();
});

test("a callback queued by an earlier session cannot count into a new session", () => {
  const { hook, monitor } = fixture();
  monitor.start();
  const stale = hook.listeners("keydown")[0];
  monitor.reset(); monitor.start();
  stale();
  hook.emit("keydown");
  assert.equal(monitor.status().session_keyboard_count, 1);
  monitor.stop();
});

test("missing module or native start failure is visible instead of silently claiming capture works", () => {
  const unavailable = createInputMonitor({ loadHook: () => { throw new Error("missing binary"); } });
  assert.equal(unavailable.start(), false);
  assert.equal(unavailable.status().state, "unavailable");
  assert.match(unavailable.status().message, /unavailable/);
  const { hook, monitor } = fixture();
  hook.start = () => { throw new Error("OS denied capture"); };
  assert.equal(monitor.start(), false);
  assert.equal(hook.stops, 0);
  assert.equal(hook.listenerCount("keydown"), 0);
});

test("native errors disable counting and detach the capture listeners", () => {
  const { hook, monitor } = fixture();
  monitor.start();
  hook.emit("error", new Error("capture stopped"));
  assert.equal(monitor.status().state, "unavailable");
  assert.equal(monitor.status().active, false);
  assert.equal(hook.listenerCount("keydown"), 0);
});

test("interval values stay inside the existing API integer limit", () => {
  const { hook, monitor } = fixture();
  monitor.start();
  for (let i = 0; i < MAX_INTERVAL_COUNT + 3; i++) hook.emit("keydown");
  assert.equal(monitor.drain().keyboard_count, MAX_INTERVAL_COUNT);
  assert.equal(monitor.status().session_keyboard_count, MAX_INTERVAL_COUNT + 3);
  monitor.stop();
});
