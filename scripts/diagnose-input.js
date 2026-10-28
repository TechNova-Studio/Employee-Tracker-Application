const path = require("node:path");
const { spawnSync } = require("node:child_process");
let executable;
try { executable = require("electron"); } catch {
  console.error("Electron is not installed. Run npm ci in the desktop-agent folder first.");
  process.exit(1);
}
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
const result = spawnSync(executable, [path.join(__dirname, "../electron/diagnose-input.js")], {
  stdio: "inherit", env,
});
if (result.error) console.error("Cannot launch Electron input test:", result.error.code || result.error.name);
if (result.signal) console.error("Electron exited before the test finished:", result.signal);
process.exitCode = result.status ?? 1;
