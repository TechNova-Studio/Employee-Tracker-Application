const test = require("node:test");
const assert = require("node:assert/strict");
const { agent } = require("../test-support/agent");

const user = { id: 7, email: "employee@example.test" };
const company = { id: 1, name: "Tenant" };
async function desktop(options = {}) {
  let nextSession = 100;
  const result = await agent({
    ...options,
    savedSession: { token: "token-7", user, company, deviceId: "desk-1" },
    get: async () => ({ data: { user, company } }),
    post: async (url, body, config) => {
      const custom = await options.post?.(url, body, config);
      if (custom !== undefined) return custom;
      return { data: url.endsWith("/agent/session/start/")
        ? { id: ++nextSession, status: "RUNNING" } : {} };
    },
  });
  await result.call("verifySession");
  return result;
}
function batches(d) {
  return d.requests.filter(([, url]) => url.endsWith("/agent/activity/batch/"));
}
function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}

test("global input starts only after the server accepts the work session", async () => {
  const d = await desktop();
  assert.equal(d.hook.starts, 0);
  d.hook.emit("keydown");
  await d.call("startSession");
  assert.equal(d.hook.starts, 1);
  assert.equal(d.windows[0].webContents.listenerCount("before-input-event"), 0);
  // No WorkPulse-window event is emitted: these arrive from the native hook
  // while another application has focus.
  for (let i = 0; i < 15; i++) d.hook.emit("keydown", { keycode: 30 });
  for (let i = 0; i < 3; i++) d.hook.emit("mousedown", { x: 10, y: 15 });
  const status = await d.call("status");
  assert.equal(status.inputCapture.session_keyboard_count, 15);
  assert.equal(status.inputCapture.session_mouse_count, 3);
  await d.tick();
  const row = batches(d)[0][2].activities[0];
  assert.equal(row.keyboard_count, 15);
  assert.equal(row.mouse_count, 3);
  assert.equal(row.duration_seconds, 60);
  assert.equal(Object.hasOwn(row, "keycode"), false);
  assert.equal(Object.hasOwn(row, "x"), false);
  await d.call("stopSession");
});

test("periodic uploads reset interval counts while the desktop retains cumulative session totals", async () => {
  const d = await desktop();
  await d.call("startSession");
  d.hook.emit("keydown"); await d.tick();
  d.hook.emit("keydown"); d.hook.emit("keydown"); await d.tick();
  assert.deepEqual(batches(d).map((r) => r[2].activities[0].keyboard_count), [1, 2]);
  const status = await d.call("status");
  assert.equal(status.inputCapture.keyboard_count, 0);
  assert.equal(status.inputCapture.session_keyboard_count, 3);
  await d.call("stopSession");
});

test("support diagnostics distinguish captured and server-saved integer counts without exposing login data", async () => {
  const d = await desktop({ post: (url, body) => {
    if (url.endsWith("/agent/activity/batch/")) return { data: { items: [body.activities[0]] } };
  } });
  await d.call("startSession");
  for (let i = 0; i < 14; i++) d.hook.emit("keydown");
  for (let i = 0; i < 5; i++) d.hook.emit("mousedown");
  await d.tick();
  const report = d.inputReport();
  assert.equal(report.app_version, require("../package.json").version);
  assert.equal(report.capture.session_keyboard_count, 14);
  assert.equal(report.last_activity_attempt.keyboard_count, 14);
  assert.equal(report.last_activity_attempt.server_keyboard_count, 14);
  assert.equal(report.last_activity_attempt.server_mouse_count, 5);
  assert.equal(report.last_activity_attempt.outcome, "uploaded");
  assert.doesNotMatch(JSON.stringify(report), /token-7|employee@example|Authorization|keycode|window_title/);
  assert.equal((await d.call("inputDiagnostics")).capture.session_mouse_count, 5);
  await d.call("logout");
  assert.equal(d.inputReport().capture.session_keyboard_count, 0);
  assert.equal(d.inputReport().last_activity_attempt, null);
});

test("a backend count mismatch is visible and never causes a duplicate upload", async () => {
  const d = await desktop({ post: url => {
    if (url.endsWith("/agent/activity/batch/")) return { data: { items: [{ keyboard_count: 1, mouse_count: 0 }] } };
  } });
  await d.call("startSession");
  d.hook.emit("keydown"); d.hook.emit("keydown"); d.hook.emit("mousedown");
  await d.tick();
  const report = d.inputReport();
  assert.equal(report.event, "upload_count_mismatch");
  assert.equal(report.last_activity_attempt.keyboard_count, 2);
  assert.equal(report.last_activity_attempt.server_keyboard_count, 1);
  assert.equal(batches(d).length, 1);
  assert.equal(d.queue().length, 0);
  await d.call("stopSession");
});

test("offline upload diagnostics keep the sent counts and HTTP status", async () => {
  const d = await desktop({ post: url => {
    if (url.endsWith("/agent/activity/batch/")) throw { response: { status: 503, data: { detail: "Unavailable" } } };
  } });
  await d.call("startSession"); d.hook.emit("keydown"); d.hook.emit("mousedown");
  await d.tick();
  const report = d.inputReport().last_activity_attempt;
  assert.equal(report.outcome, "queued_after_activity");
  assert.equal(report.http_status, 503);
  assert.equal(report.keyboard_count, 1);
  assert.equal(d.queue().length, 1);
  await d.call("stopSession");
});

test("native capture errors remain diagnosable when the employee UI has no input-counter display", async () => {
  const d = await desktop({ inputFailure: true });
  await d.call("startSession");
  const report = d.inputReport();
  assert.equal(report.capture.state, "unavailable");
  assert.equal(report.capture.error_detail, "native input unavailable");
  assert.equal(report.capture.active, false);
  assert.equal(report.app_version, require("../package.json").version);
  await d.call("logout");
  assert.equal(d.inputReport().capture.error_code, "");
});

test("punch-out disables capture before a slow final upload and flushes a short session", async () => {
  const uploading = deferred();
  let d;
  d = await desktop({ post: (url) => {
    if (url.endsWith("/agent/heartbeat/")) {
      assert.equal(d.hook.running, false);
      return uploading.promise;
    }
  } });
  await d.call("startSession");
  d.advance(25000);
  d.hook.emit("keydown"); d.hook.emit("mousedown");
  const stopping = d.call("stopSession");
  assert.equal(d.hook.running, false);
  d.hook.emit("keydown");
  uploading.resolve({ data: {} });
  await stopping;
  assert.equal(batches(d).length, 1);
  assert.equal(batches(d)[0][2].activities[0].keyboard_count, 1);
  assert.equal(batches(d)[0][2].activities[0].duration_seconds, 25);
  assert.equal((await d.call("status")).runningSession, null);
  assert.equal(d.inputReport().session_running, false);
  assert.equal(d.timers.size, 0);
});

test("each new punch-in begins with zero session counts", async () => {
  const d = await desktop();
  await d.call("startSession"); d.hook.emit("keydown");
  await d.call("stopSession");
  d.hook.emit("keydown");
  await d.call("startSession");
  assert.equal((await d.call("status")).inputCapture.session_keyboard_count, 0);
  await d.call("stopSession");
});

test("an in-flight timer and punch-out send each count exactly once", async () => {
  const firstHeartbeat = deferred();
  const entered = deferred();
  let held = false;
  const d = await desktop({ post: (url) => {
    if (url.endsWith("/agent/heartbeat/") && !held) {
      held = true;
      entered.resolve();
      return firstHeartbeat.promise;
    }
  } });
  await d.call("startSession");
  d.hook.emit("keydown"); d.hook.emit("keydown");
  const tick = d.tick();
  await entered.promise;
  d.hook.emit("keydown"); d.hook.emit("keydown"); d.hook.emit("keydown");
  const stop = d.call("stopSession");
  assert.equal(d.hook.running, false);
  firstHeartbeat.resolve({ data: {} });
  await Promise.all([tick, stop]);
  assert.deepEqual(batches(d).map((r) => r[2].activities[0].keyboard_count), [2, 3]);
  assert.equal(d.requests.filter(([, url]) => url.endsWith("/agent/session/stop/")).length, 1);
});

test("screen lock and sleep pause input; capture resumes only after both are cleared", async () => {
  const d = await desktop();
  await d.call("startSession"); d.hook.emit("keydown");
  d.powerMonitor.emit("lock-screen");
  d.powerMonitor.emit("suspend");
  d.hook.emit("keydown");
  d.powerMonitor.emit("resume");
  assert.equal(d.hook.running, false);
  assert.equal((await d.call("status")).inputCapture.state, "paused");
  assert.equal(d.inputReport().capture.state, "paused");
  d.powerMonitor.emit("unlock-screen");
  assert.equal(d.hook.running, true);
  d.hook.emit("keydown");
  assert.equal((await d.call("status")).inputCapture.session_keyboard_count, 2);
  await d.call("stopSession");
  d.powerMonitor.emit("unlock-screen");
  assert.equal(d.hook.running, false);
});

test("a rejected attendance/policy gate never starts the OS input hook", async () => {
  const d = await desktop({ post: (url) => {
    if (url.endsWith("/agent/session/start/")) throw { response: { status: 403,
      data: { blocked_reason: "POLICY_NOT_ACCEPTED" } } };
  } });
  const result = await d.call("startSession");
  assert.equal(result.blocked, true);
  assert.equal(d.hook.starts, 0);
  assert.equal((await d.call("status")).inputCapture.session_keyboard_count, 0);
});

for (const reason of ["POLICY_NOT_ACCEPTED", "EMPLOYEE_INACTIVE", "OUTDATED_AGENT"]) {
  test(`${reason} stops input capture during a server-blocked heartbeat`, async () => {
    const d = await desktop({ post: (url) => {
      if (url.endsWith("/agent/heartbeat/")) throw { response: { status: 403,
        data: { blocked_reason: reason, version: {} } } };
    } });
    await d.call("startSession");
    d.hook.emit("keydown");
    await d.tick();
    assert.equal(d.hook.running, false);
    assert.equal((await d.call("status")).runningSession, null);
    d.hook.emit("keydown");
    assert.equal((await d.call("status")).inputCapture.session_keyboard_count, 1);
  });
}

test("401 session expiry immediately disables capture", async () => {
  const d = await desktop({ post: (url) => {
    if (url.endsWith("/agent/heartbeat/")) throw { response: { status: 401,
      data: { detail: "Invalid token" } } };
  } });
  await d.call("startSession");
  await d.tick();
  assert.equal(d.hook.running, false);
  assert.equal((await d.call("status")).currentUser, null);
});

test("a missing/denied native hook reports unavailable while the attendance session remains usable", async () => {
  const d = await desktop({ inputFailure: true });
  await d.call("startSession");
  const status = await d.call("status");
  assert.equal(status.runningSession.id, 101);
  assert.equal(status.inputCapture.state, "unavailable");
  assert.match(status.inputCapture.message, /unavailable/);
  await d.call("stopSession");
});

test("sign-out and application exit release native listeners and timers", async () => {
  const d = await desktop();
  await d.call("startSession");
  await d.call("logout");
  assert.equal(d.hook.running, false);
  assert.equal(d.hook.listenerCount("keydown"), 0);
  assert.equal(d.timers.size, 0);
  const another = await desktop();
  await another.call("startSession");
  another.application.emit("will-quit");
  assert.equal(another.hook.running, false);
  assert.equal(another.timers.size, 0);
});

test("packaged startup uses the built UI even if the PC has NODE_ENV=development", async () => {
  const d = await desktop({ packaged: true });
  assert.match(d.windows[0].loadedFile, /dist[/\\]index.html$/);
  assert.equal(d.windows[0].loadedURL, undefined);
});

test("a late start response after logout cannot enable capture or change employee ownership", async () => {
  const pending = deferred();
  const entered = deferred();
  const d = await desktop({ post: (url) => {
    if (url.endsWith("/agent/session/start/")) {
      entered.resolve();
      return pending.promise;
    }
  } });
  const starting = d.call("startSession");
  await entered.promise;
  await d.call("logout");
  pending.resolve({ data: { id: 101, status: "RUNNING" } });
  await assert.rejects(starting, /login changed/);
  assert.equal(d.hook.starts, 0);
  assert.equal((await d.call("status")).runningSession, null);
  assert.equal(d.queue()[0].payload.session_id, 101);
  assert.match(d.queue()[0].owner, /:1:7$/);
});

test("repeated punch-in clicks share one server request and one native listener", async () => {
  const d = await desktop();
  const sessions = await Promise.all([d.call("startSession"), d.call("startSession")]);
  assert.equal(sessions[0].id, sessions[1].id);
  assert.equal(d.requests.filter(([, url]) => url.endsWith("/agent/session/start/")).length, 1);
  assert.equal(d.hook.starts, 1);
  assert.equal(d.hook.listenerCount("keydown"), 1);
  await d.call("stopSession");
});

test("zero keyboard and mouse counts do not mark an otherwise active employee idle", async () => {
  const d = await desktop();
  await d.call("startSession");
  await d.tick();
  const heartbeat = d.requests.find(([, url]) => url.endsWith("/agent/heartbeat/"))[2];
  assert.equal(heartbeat.active_seconds, 60);
  assert.equal(heartbeat.is_idle, false);
  assert.equal(batches(d)[0][2].activities[0].keyboard_count, 0);
  await d.call("stopSession");
});

test("unlocking during a slow punch-out cannot restart input capture", async () => {
  const uploading = deferred();
  const d = await desktop({ post: (url) => {
    if (url.endsWith("/agent/heartbeat/")) return uploading.promise;
  } });
  await d.call("startSession");
  d.hook.emit("keydown");
  const stopping = d.call("stopSession");
  d.powerMonitor.emit("lock-screen");
  d.powerMonitor.emit("unlock-screen");
  assert.equal(d.hook.running, false);
  assert.equal(d.hook.starts, 1);
  uploading.resolve({ data: {} });
  await stopping;
});

test("sign-out clears session counters before another employee can see them", async () => {
  const d = await desktop();
  await d.call("startSession");
  d.hook.emit("keydown"); d.hook.emit("mousedown");
  await d.call("logout");
  const status = await d.call("status");
  assert.equal(status.inputCapture.session_keyboard_count, 0);
  assert.equal(status.inputCapture.session_mouse_count, 0);
  assert.equal(status.currentUser, null);
});
