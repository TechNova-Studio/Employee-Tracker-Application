// Run before packaging, so a missing native binary cannot become an installer
// that silently shows zero input counts on another PC.
const fs = require("node:fs");
const path = require("node:path");

function checkInputPackage({ root = path.join(__dirname, ".."), target = "win32", arch = "x64" } = {}) {
  const directory = path.join(root, "node_modules", "uiohook-napi");
  const manifest = path.join(directory, "package.json");
  const binary = path.join(directory, "prebuilds", `${target}-${arch}`, "node.napi.node");
  if (!fs.existsSync(manifest) || !fs.existsSync(binary)) {
    throw new Error(`Input capture binary missing for ${target}-${arch}. Run npm ci before rebuilding the agent.`);
  }
  const pkg = JSON.parse(fs.readFileSync(manifest, "utf8"));
  if (pkg.version !== "1.5.4") throw new Error("Expected the pinned uiohook-napi 1.5.4 package. Run npm ci.");
  const executable = fs.readFileSync(binary);
  if (target === "win32" && (executable[0] !== 0x4d || executable[1] !== 0x5a)) {
    throw new Error("The Windows input capture binary is invalid. Reinstall dependencies with npm ci.");
  }
  return binary;
}

if (require.main === module) {
  try {
    const target = process.argv[2] || process.platform;
    const arch = process.argv[3] || process.arch;
    checkInputPackage({ target, arch });
    console.log(`Input capture package verified for ${target}-${arch}.`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

module.exports = { checkInputPackage };
