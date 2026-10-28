const fs = require("node:fs");
const path = require("node:path");

const WINDOWS_SCREENSHOT_ASSETS = ["screenCapture_1.3.2.bat", "app.manifest"];
function checkScreenshotPackage({ root = path.join(__dirname, "..") } = {}) {
  const directory = path.join(root, "node_modules", "screenshot-desktop", "lib", "win32");
  const files = WINDOWS_SCREENSHOT_ASSETS.map(name => path.join(directory, name));
  for (const file of files) {
    if (!fs.existsSync(file) || !fs.statSync(file).isFile() || fs.statSync(file).size === 0)
      throw new Error(`Windows screenshot helper missing or empty: ${path.basename(file)}. Run npm ci and rebuild with screenshot-desktop/lib/win32 unpacked.`);
  }
  return files;
}
if (require.main === module) {
  try { checkScreenshotPackage(); console.log("Windows screenshot helper files verified."); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = { checkScreenshotPackage, WINDOWS_SCREENSHOT_ASSETS };
