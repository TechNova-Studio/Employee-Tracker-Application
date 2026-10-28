// Aggregate counts only. Native event payloads (keys, characters and pointer
// coordinates) never leave these callbacks and are never saved or sent by IPC.
const MAX_INTERVAL_COUNT = 86400; // Existing WorkPulse activity API limit.

function createInputMonitor({
  loadHook = () => require("uiohook-napi").uIOhook,
  now = Date.now,
  onActivity = () => {},
  onError = () => {},
} = {}) {
  let hook = null;
  let active = false;
  let state = "stopped";
  let message = "";
  let errorCode = "";
  let errorDetail = "";
  let keyboardCount = 0;
  let mouseCount = 0;
  let sessionKeyboardCount = 0;
  let sessionMouseCount = 0;
  let lastInputAt = null;
  let generation = 0;
  let attachedListeners = [];

  function activity() {
    if (!active) return false;
    lastInputAt = now();
    onActivity();
    return true;
  }
  function keyDown() {
    if (!activity()) return;
    keyboardCount = Math.min(MAX_INTERVAL_COUNT, keyboardCount + 1);
    sessionKeyboardCount = Math.min(Number.MAX_SAFE_INTEGER, sessionKeyboardCount + 1);
  }
  function mouseDown() {
    if (!activity()) return;
    mouseCount = Math.min(MAX_INTERVAL_COUNT, mouseCount + 1);
    sessionMouseCount = Math.min(Number.MAX_SAFE_INTEGER, sessionMouseCount + 1);
  }
  function pointerActivity() {
    // Movement and scrolling affect the idle fallback, but are not mouse clicks.
    activity();
  }
  function describeFailure(error, phase) {
    errorCode = typeof error?.code === "string" ? error.code.slice(0, 100) : "INPUT_CAPTURE_FAILED";
    // Native initialization errors contain module/OS details, not input data.
    // Keep one bounded line; never log a raw event or error object/stack.
    errorDetail = String(error?.message || "Native input capture failed.").split(/\r?\n/)[0].slice(0, 500);
    message = `Keyboard and mouse counts are unavailable (${errorCode}).`;
    try { onError({ phase, code: errorCode, detail: errorDetail }); } catch { /* Diagnostics cannot interrupt the session. */ }
  }
  function failed(error) {
    stop();
    state = "unavailable";
    describeFailure(error, "runtime");
  }
  const listeners = [
    ["keydown", keyDown],
    ["mousedown", mouseDown],
    ["mousemove", pointerActivity],
    ["wheel", pointerActivity],
    ["error", failed],
  ];
  function removeListeners() {
    if (!hook) return;
    for (const [event, listener] of attachedListeners) hook.removeListener(event, listener);
    attachedListeners = [];
  }
  function start() {
    if (active) return true;
    message = "";
    errorCode = errorDetail = "";
    try {
      if (!hook) hook = loadHook();
      if (!hook || typeof hook.start !== "function" ||
          typeof hook.stop !== "function" || typeof hook.on !== "function" ||
          typeof hook.removeListener !== "function") {
        throw new Error("Input capture is not installed.");
      }
      const ticket = ++generation;
      for (const [event, listener] of listeners) {
        const guarded = error => {
          if (active && ticket === generation) {
            // The only payload read is an initialization/runtime Error.
            // Keyboard/mouse handlers deliberately receive no raw event.
            if (event === "error") listener(error);
            else listener();
          }
        };
        attachedListeners.push([event, guarded]);
        hook.on(event, guarded);
      }
      active = true;
      hook.start();
      if (!active) return false;
      state = "running";
      return true;
    } catch (error) {
      // Native start reports initialization failure itself. Do not call native
      // stop after a failed start, when no operating-system hook exists.
      active = false;
      generation++;
      if (hook && typeof hook.removeListener === "function") removeListeners();
      state = "unavailable";
      describeFailure(error, "start");
      return false;
    }
  }
  function stop() {
    const wasActive = active;
    active = false; // Reject already queued callbacks before detaching the hook.
    generation++;
    if (hook && typeof hook.removeListener === "function") removeListeners();
    if (wasActive) {
      try { hook.stop(); } catch { /* Capture remains disabled in this agent. */ }
    }
    state = "stopped";
  }
  function pause() {
    stop();
    state = "paused";
  }
  function reset() {
    stop();
    keyboardCount = mouseCount = sessionKeyboardCount = sessionMouseCount = 0;
    lastInputAt = null;
    message = "";
    errorCode = errorDetail = "";
  }
  function drain() {
    const counts = { keyboard_count: keyboardCount, mouse_count: mouseCount };
    keyboardCount = mouseCount = 0;
    return counts;
  }
  function status() {
    return {
      state,
      active,
      message,
      error_code: errorCode,
      error_detail: errorDetail,
      keyboard_count: keyboardCount,
      mouse_count: mouseCount,
      session_keyboard_count: sessionKeyboardCount,
      session_mouse_count: sessionMouseCount,
      last_input_at: lastInputAt,
    };
  }
  return { start, stop, pause, reset, drain, status };
}

module.exports = { createInputMonitor, MAX_INTERVAL_COUNT };
