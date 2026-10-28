const path = require("node:path");
const { checkInputPackage } = require("./check-input-package");
const { checkScreenshotPackage } = require("./check-screenshot-package");

// electron-builder executes this after creating the app and before NSIS runs.
module.exports = async function verifyPackagedInput(context) {
  if (context.electronPlatformName !== "win32") return;
  checkInputPackage({
    root: path.join(context.appOutDir, "resources", "app.asar.unpacked"),
    target: "win32",
    arch: "x64",
  });
  checkScreenshotPackage({ root: path.join(context.appOutDir, "resources", "app.asar.unpacked") });
  console.log("Packaged Windows input capture binary verified.");
  console.log("Packaged Windows screenshot BAT and manifest verified outside ASAR.");
};
