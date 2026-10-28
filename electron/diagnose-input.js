const { createInputMonitor } = require("./input-monitor");

// Explicit local 30-second test, using the production monitor in Electron.
// No login, HTTP calls, screenshots, event injection or typed content storage.
function createInputCheck({ monitor = createInputMonitor(), log = console.log,
  complete = () => {}, durationMs = 30000, schedule = setTimeout, repeat = setInterval,
  cancelSchedule = clearTimeout, cancelRepeat = clearInterval } = {}) {
  let started = false, done = false, timer, ticker, resolve;
  const finished = new Promise(r => { resolve = r; });
  function snapshot() {
    const s = monitor.status();
    return { capture_state: s.state, keyboard_count: s.session_keyboard_count,
      mouse_count: s.session_mouse_count, activity_received: s.last_input_at !== null,
      error_code: s.error_code || "", error_detail: s.error_detail || "" };
  }
  function finish(cancelled = false) {
    if (done) return;
    done = true;
    cancelSchedule(timer); cancelRepeat(ticker);
    const s = snapshot();
    monitor.stop();
    const nativeFailed = s.capture_state === "unavailable";
    const passed = s.keyboard_count >= 2 && s.mouse_count >= 2;
    const result = cancelled ? "CANCELLED" : nativeFailed ? "NATIVE_CAPTURE_FAILED" : passed ? "PASS"
      : s.keyboard_count || s.mouse_count ? "PARTIAL_INPUT" : "NO_KEYBOARD_OR_CLICKS";
    const report = { result, exit_code: cancelled ? 130 : nativeFailed ? 1 : passed ? 0 : 2, ...s };
    log("INPUT_CHECK_RESULT", JSON.stringify(report));
    resolve(report); complete(report);
  }
  function start() {
    if (started || done) return;
    started = true;
    log("WORKPULSE_INPUT_CHECK_START", "30-second local test. Switch to Notepad, type 10+ letters and click at least twice. Mouse movement is not a click. No typed text is saved or sent.");
    if (!monitor.start()) { finish(); return; }
    ticker = repeat(() => {
      if (monitor.status().state === "unavailable") { finish(); return; }
      log("INPUT_PROGRESS", JSON.stringify(snapshot()));
    }, 5000);
    timer = schedule(() => finish(), durationMs);
  }
  return { start, cancel: () => finish(true), finished };
}

function startElectronInputCheck() {
  const { app } = require("electron");
  let check;
  app.whenReady().then(() => {
    console.log("INPUT_RUNTIME", JSON.stringify({ agent_version: require("../package.json").version,
      electron: process.versions.electron, node: process.versions.node,
      platform: process.platform, arch: process.arch }));
    check = createInputCheck({ complete: report => app.exit(report.exit_code) });
    check.start();
  }).catch(error => { console.error("INPUT_CHECK_START_FAILED", error.code || error.name); app.exit(1); });
  process.once("SIGINT", () => check ? check.cancel() : app.exit(130));
  process.once("SIGTERM", () => check ? check.cancel() : app.exit(130));
  app.once("before-quit", () => check?.cancel());
}

if (require.main === module) startElectronInputCheck();
module.exports = { createInputCheck };
