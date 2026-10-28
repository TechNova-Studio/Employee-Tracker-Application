const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const { createServer } = require("vite");
let server;
let DashboardScreen;

test.before(async () => {
  server = await createServer({
    root: path.join(__dirname, ".."),
    server: { middlewareMode: true, watch: null },
    appType: "custom",
    optimizeDeps: { noDiscovery: true },
  });
  ({ DashboardScreen } = await server.ssrLoadModule("/src/screens/DashboardScreen.jsx"));
});
test.after(async () => { await server?.close(); });
test("the employee attendance screen does not display input counters or capture diagnostics", () => {
  for (const state of ["running", "unavailable", "paused", "stopped"]) {
    const html = renderToStaticMarkup(React.createElement(DashboardScreen, {
      status: { runningSession: state === "stopped" ? null : { id: 1 },
        inputCapture: { state, active: state === "running", session_keyboard_count: 27185,
          session_mouse_count: 87653, message: "NATIVE_CAPTURE_ERROR_PRIVATE_SUPPORT" } },
      cfg: { PLATFORM: "windows" },
    }));
    assert.doesNotMatch(html, /27185|87653|Key presses|Mouse clicks|Input counting|NATIVE_CAPTURE_ERROR_PRIVATE_SUPPORT/);
    assert.match(html, /Shift Attendance/);
    assert.match(html, /Attendance Overview/);
    assert.match(html, state === "stopped" ? /Punch In/ : /Punch Out/);
  }
});
