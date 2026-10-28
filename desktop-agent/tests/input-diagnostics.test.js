const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { createInputMonitor } = require("../electron/input-monitor");
const { createInputCheck } = require("../electron/diagnose-input");
const { inputReport } = require("../electron/input-report");

function fixture(failure) {
  const hook = new EventEmitter();
  let stops = 0;
  hook.start = () => { if (failure) throw Object.assign(Error("Native module failed\nprivate stack"), { code: "ERR_DLOPEN_FAILED" }); };
  hook.stop = () => { stops++; };
  const monitor = createInputMonitor({ loadHook: () => hook });
  const logs = [], scheduled = new Set();
  let end, progress;
  const check = createInputCheck({ monitor, log: (...args) => logs.push(args),
    schedule: f => { end = f; scheduled.add(f); return f; },
    repeat: f => { progress = f; scheduled.add(f); return f; },
    cancelSchedule: f => scheduled.delete(f), cancelRepeat: f => scheduled.delete(f) });
  return { hook, monitor, check, logs, scheduled, end: () => end(), progress: () => progress(), stops: () => stops };
}

test("native self-check accepts actual received counts and never reads raw input payloads", async () => {
  const d = fixture(); d.check.start();
  const raw = new Proxy({}, { get() { throw Error("Read raw input"); } });
  for (let i = 0; i < 12; i++) d.hook.emit("keydown", raw);
  for (let i = 0; i < 3; i++) d.hook.emit("mousedown", raw);
  d.progress(); d.end();
  const result = await d.check.finished;
  assert.equal(result.result, "PASS"); assert.equal(result.keyboard_count, 12);
  assert.equal(result.mouse_count, 3); assert.equal(result.exit_code, 0);
  assert.equal(d.stops(), 1); assert.equal(d.scheduled.size, 0);
  assert.doesNotMatch(JSON.stringify(d.logs), /keycode|coordinates|Authorization|password/);
});

test("zero input or pointer movement alone cannot pass the self-check", async () => {
  const d = fixture(); d.check.start(); d.hook.emit("mousemove"); d.hook.emit("wheel"); d.end();
  const result = await d.check.finished;
  assert.equal(result.result, "NO_KEYBOARD_OR_CLICKS"); assert.equal(result.exit_code, 2);
  assert.equal(result.activity_received, true);
});

test("partial input does not assert that both devices work", async () => {
  const d = fixture(); d.check.start(); d.hook.emit("keydown"); d.end();
  const result = await d.check.finished;
  assert.equal(result.result, "PARTIAL_INPUT"); assert.equal(result.exit_code, 2);
});

test("initialization failure reports its bounded native error with no timers left", async () => {
  const d = fixture(true); d.check.start(); const result = await d.check.finished;
  assert.equal(result.result, "NATIVE_CAPTURE_FAILED"); assert.equal(result.error_code, "ERR_DLOPEN_FAILED");
  assert.equal(result.error_detail, "Native module failed"); assert.equal(d.scheduled.size, 0);
  assert.equal(result.exit_code, 1);
});

test("runtime failure ends the test and releases the native hook", async () => {
  const d = fixture(); d.check.start();
  d.hook.emit("error", Object.assign(Error("Hook stopped"), { code: "UIOHOOK_FAILURE" })); d.progress();
  const result = await d.check.finished;
  assert.equal(result.result, "NATIVE_CAPTURE_FAILED"); assert.equal(result.error_code, "UIOHOOK_FAILURE");
  assert.equal(d.scheduled.size, 0);
});

test("cancel stops the test once and clears scheduled work", async () => {
  const d = fixture(); d.check.start(); d.check.cancel(); d.check.cancel();
  assert.equal((await d.check.finished).exit_code, 130);
  assert.equal(d.stops(), 1); assert.equal(d.scheduled.size, 0);
});

test("support snapshots omit users, authorization, URLs and raw native events", () => {
  const report = inputReport({ event: "activity_uploaded", version: "1.0.3", platform: "windows", arch: "x64", running: true,
    capture: { state: "running", active: true, session_keyboard_count: 27, session_mouse_count: 5,
      token: "PRIVATE_TOKEN", keycode: "PRIVATE_KEY", user: "PRIVATE_USER" },
    attempt: { outcome: "uploaded", keyboard_count: 27, mouse_count: 5, server_keyboard_count: 27,
      server_mouse_count: 5, Authorization: "PRIVATE_HEADER", url: "PRIVATE_URL" } });
  assert.doesNotMatch(JSON.stringify(report), /PRIVATE_/);
  assert.equal(report.last_activity_attempt.server_keyboard_count, 27);
  assert.equal(report.capture.session_mouse_count, 5);
});
