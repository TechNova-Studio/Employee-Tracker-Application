const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { checkInputPackage } = require("../scripts/check-input-package");
const verifyPackagedInput = require("../scripts/verify-packaged-input");

test("packaging fails when the global input dependency or Windows binary is missing", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "workpulse-input-package-"));
  try {
    assert.throws(() => checkInputPackage({ root }), /binary missing/);
    await assert.rejects(verifyPackagedInput({ appOutDir: root, electronPlatformName: "win32" }), /binary missing/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test("the installed pinned package contains the Windows x64 native binary", () => {
  const binary = checkInputPackage();
  assert.match(binary, /win32-x64[/\\]node\.napi\.node$/);
  const data = fs.readFileSync(binary);
  const pe = data.readUInt32LE(0x3c);
  assert.equal(data.subarray(pe, pe + 4).toString("binary"), "PE\u0000\u0000");
  assert.equal(data.readUInt16LE(pe + 4), 0x8664);
});
