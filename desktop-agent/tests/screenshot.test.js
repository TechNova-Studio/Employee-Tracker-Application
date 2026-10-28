const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { agent } = require("../test-support/agent");
const { checkScreenshotPackage, WINDOWS_SCREENSHOT_ASSETS } = require("../scripts/check-screenshot-package");

async function desktop(options = {}) {
  const user = { id: 85, email: "employee@example.test", profile: { role: "EMPLOYEE", company: 1 } }, company = { id: 1, name: "Glutape" };
  const d = await agent({ ...options,
    savedSession: { token: "employee-token", user, company, deviceId: "employee-pc" },
    get: async () => ({ data: { user, company } }),
    post: async (url, body, config) => {
      const custom = await options.post?.(url, body, config);
      if (custom !== undefined) return custom;
      return { data: url.endsWith("/agent/session/start/") ? { id: 100, status: "RUNNING" } : {} };
    } });
  await d.call("verifySession");
  return d;
}
const uploads = d => d.requests.filter(([, url]) => url.endsWith("/agent/screenshots/upload/"));

test("Windows screenshot packaging requires BOTH helper files outside ASAR", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "workpulse-ss-package-"));
  const dir = path.join(root, "node_modules/screenshot-desktop/lib/win32");
  fs.mkdirSync(dir, { recursive: true });
  try {
    assert.throws(() => checkScreenshotPackage({ root }), /screenCapture.*missing|missing.*screenCapture/);
    fs.writeFileSync(path.join(dir, WINDOWS_SCREENSHOT_ASSETS[0]), "capture");
    assert.throws(() => checkScreenshotPackage({ root }), /app.manifest/);
    fs.writeFileSync(path.join(dir, WINDOWS_SCREENSHOT_ASSETS[1]), "manifest");
    assert.equal(checkScreenshotPackage({ root }).length, 2);
    fs.writeFileSync(path.join(dir, WINDOWS_SCREENSHOT_ASSETS[1]), "");
    assert.throws(() => checkScreenshotPackage({ root }), /empty/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test("the source contains screenshot helpers and the builder explicitly unpacks them", () => {
  assert.equal(checkScreenshotPackage().length, 2);
  assert.ok(require("../package.json").build.asarUnpack.includes("node_modules/screenshot-desktop/lib/win32/**/*"));
});

test("an EMPLOYEE session captures at startup and interval using that employee's token/device", async () => {
  let captures = 0;
  const d = await desktop({ screenshot: async () => { captures++; return "fake-png-bytes"; } });
  await d.call("startSession");
  assert.equal(captures, 0);
  await d.screenshotTick(true); await d.screenshotTick();
  assert.equal(captures, 2); assert.equal(uploads(d).length, 2);
  const form = uploads(d)[0][2];
  assert.equal(form.parts.find(([name]) => name === "device_id")[1], (await d.call("status")).deviceId);
  assert.equal(form.parts.find(([name]) => name === "session_id")[1], "100");
  assert.equal(uploads(d)[0][3].headers.Authorization, "Token employee-token");
  assert.equal(d.screenshotReport().last_attempt.state, "uploaded");
  assert.equal(d.tempScreenshots().length, 0);
  await d.call("stopSession");
});

test("a missing capture helper is diagnosed instead of silently returning", async () => {
  const d = await desktop(); await d.call("startSession"); await d.screenshotTick(true);
  const report = await d.call("screenshotDiagnostics");
  assert.equal(report.module_available, false); assert.equal(report.last_attempt.phase, "module");
  assert.equal(report.last_attempt.state, "failed"); assert.equal(uploads(d).length, 0);
  await d.call("logout");
});

test("packaging/capture ENOENT errors retain diagnostic details without fake queued screenshots", async () => {
  const d = await desktop({ screenshot: async () => { throw Object.assign(Error("Windows capture BAT missing"), { code: "ENOENT" }); } });
  await d.call("startSession"); await d.screenshotTick(true);
  const error = d.screenshotReport().last_attempt;
  assert.equal(error.phase, "capture"); assert.equal(error.error_code, "ENOENT");
  assert.equal(error.detail, "Windows capture BAT missing");
  assert.equal(d.queue().length, 0); assert.equal(d.tempScreenshots().length, 0);
  await d.call("logout");
});

test("backend 501 storage failures are recorded and a later capture can still succeed", async () => {
  let fail = true;
  const d = await desktop({ screenshot: async () => "fake-png", post: url => {
    if (url.endsWith("/agent/screenshots/upload/") && fail) throw { response: { status: 501, data: { detail: "Screenshot storage is not configured" } } };
  } });
  await d.call("startSession"); await d.screenshotTick(true);
  const error = d.screenshotReport().last_attempt;
  assert.equal(error.phase, "upload"); assert.equal(error.http_status, 501);
  assert.equal(error.detail, "Screenshot storage is not configured");
  assert.equal(d.queue().length, 0); assert.equal(d.tempScreenshots().length, 0);
  assert.doesNotMatch(JSON.stringify(d.screenshotReport()), /employee-token|employee@example|fake-png/);
  fail = false; await d.screenshotTick();
  assert.equal(d.screenshotReport().last_attempt.state, "uploaded");
  await d.call("logout"); assert.deepEqual(d.screenshotReport(), {});
});

test("screen lock blocks screenshot capture until unlock", async () => {
  let captures = 0;
  const d = await desktop({ screenshot: async () => { captures++; return "fake-png"; } });
  await d.call("startSession"); d.powerMonitor.emit("lock-screen");
  await d.screenshotTick(true); assert.equal(captures, 0);
  d.powerMonitor.emit("unlock-screen"); await d.screenshotTick(); assert.equal(captures, 1);
  await d.call("logout");
});

test("a capture pending during Punch Out cannot upload after capture permission is withdrawn", async () => {
  let resolve;
  const image = new Promise(r => { resolve = r; });
  const d = await desktop({ screenshot: () => image });
  await d.call("startSession"); const capture = d.screenshotTick(true);
  await d.call("stopSession"); resolve("fake-png"); await capture;
  assert.equal(uploads(d).length, 0); assert.equal(d.tempScreenshots().length, 0);
});
