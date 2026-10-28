const path = require("node:path");

// Windows safeStorage uses OS encryption. Never write bearer tokens as plain JSON.
function createSessionStore({ fs, directory, safeStorage }) {
  const metadata = path.join(directory, "session.json");
  const tokenFile = path.join(directory, "session-token.enc");
  let memoryToken = "";
  let encryptionFailed = false;
  function persistent() {
    try {
      return (
        !encryptionFailed &&
        !!safeStorage?.isEncryptionAvailable() &&
        safeStorage?.getSelectedStorageBackend?.() !== "basic_text"
      );
    } catch {
      return false;
    }
  }
  function save(data) {
    const { token = "", ...rest } = data;
    memoryToken = token;
    // Clear legacy plaintext first. If encryption is unavailable, keep token in memory only.
    fs.writeFileSync(metadata, JSON.stringify(rest, null, 2));
    if (token && persistent()) {
      try {
        fs.writeFileSync(
          tokenFile,
          safeStorage.encryptString(token).toString("base64"),
          "utf8",
        );
      } catch {
        encryptionFailed = true;
        if (fs.existsSync(tokenFile)) fs.unlinkSync(tokenFile);
      }
    } else if (fs.existsSync(tokenFile)) fs.unlinkSync(tokenFile);
  }
  function load() {
    let data = {};
    try {
      data = JSON.parse(fs.readFileSync(metadata, "utf8"));
    } catch {}
    if (typeof data.token === "string" && data.token) {
      const legacy = data.token;
      save(data); // Migrate a previously saved plaintext token without another login.
      return { ...data, token: legacy };
    }
    let token = memoryToken;
    try {
      if (persistent() && fs.existsSync(tokenFile))
        token = safeStorage.decryptString(
          Buffer.from(fs.readFileSync(tokenFile, "utf8"), "base64"),
        );
    } catch {
      token = "";
    }
    return { ...data, token };
  }
  return { save, load, persistent };
}
module.exports = { createSessionStore };
