const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { EventEmitter } = require("node:events");
const { createInputMonitor } = require("../electron/input-monitor");

const source = fs.readFileSync(path.join(__dirname, "../electron/main.js"), "utf8");

async function agent({ savedSession, savedQueue, get, post, inputFailure, screenshot, packaged = false } = {}) {
  const files = new Map();
  const norm = (p) => path.normalize(p);
  const clock = { value: 1000000 };
  const timers = new Map();
  let timerId = 0;
  if (savedSession) {
    const { token, ...rest } = savedSession;
    files.set(norm("/agent/session.json"), JSON.stringify(rest));
    if (token) files.set(norm("/agent/session-token.enc"), Buffer.from(token).toString("base64"));
  }
  if (savedQueue) files.set(norm("/agent/offline-queue.json"), JSON.stringify(savedQueue));
  const handlers = new Map();
  const requests = [];
  const events = [];
  const windows = [];
  const logs = [];
  const disk = {
    readFileSync: (name) => {
      const k = norm(name);
      if (!files.has(k)) throw new Error("ENOENT");
      return files.get(k);
    },
    writeFileSync: (name, value) => files.set(norm(name), String(value)),
    existsSync: (name) => files.has(norm(name)),
    unlinkSync: (name) => files.delete(norm(name)),
    createReadStream: name => ({ filename: norm(name) }),
  };
  const hook = new EventEmitter();
  hook.starts = 0;
  hook.stops = 0;
  hook.running = false;
  hook.start = () => {
    hook.starts++;
    if (inputFailure) throw new Error("native input unavailable");
    hook.running = true;
  };
  hook.stop = () => { hook.stops++; hook.running = false; };
  class Window extends EventEmitter {
    constructor() {
      super();
      this.webContents = new EventEmitter();
      this.webContents.send = (name, ...args) => events.push([name, ...args]);
      windows.push(this);
    }
    loadFile(value) { this.loadedFile = value; }
    loadURL(value) { this.loadedURL = value; }
    destroy() {}
  }
  const application = new EventEmitter();
  Object.assign(application, {
    isPackaged: packaged,
    getVersion: () => require("../package.json").version,
    getPath: (name) => name === "userData" ? "/agent" : "/tmp",
    whenReady: () => Promise.resolve(),
    quit() {},
  });
  const powerMonitor = new EventEmitter();
  powerMonitor.getSystemIdleTime = () => 0;
  const electron = {
    app: application,
    BrowserWindow: Window,
    ipcMain: { handle: (name, handler) => handlers.set(name, handler) },
    dialog: {}, powerMonitor, shell: {},
    safeStorage: {
      isEncryptionAvailable: () => true,
      getSelectedStorageBackend: () => "dpapi",
      encryptString: (str) => Buffer.from(str),
      decryptString: (buf) => buf.toString(),
    },
  };
  const axios = {
    get: async (url, options) => {
      requests.push(["GET", url, options]);
      return get ? get(url, options) : { data: { product: "BOLD WorkPulse" } };
    },
    post: async (url, body, options) => {
      requests.push(["POST", url, body, options]);
      return post ? post(url, body, options) : { data: {} };
    },
  };
  class ClockDate extends Date {
    constructor(...args) { super(...(args.length ? args : [clock.value])); }
    static now() { return clock.value; }
  }
  vm.runInNewContext(source, {
    require(name) {
      if (name === "electron") return electron;
      if (name === "fs") return disk;
      if (name === "axios") return axios;
      if (name === "os") return { networkInterfaces: () => ({}), hostname: () => "TEST-PC" };
      if (name === "./input-monitor") return {
        createInputMonitor: (options) => createInputMonitor({ ...options, loadHook: () => hook, now: () => clock.value }),
      };
      if (name === "screenshot-desktop") {
        if (screenshot) return screenshot;
        throw new Error("screenshot helper unavailable");
      }
      if (name === "active-win") throw new Error("optional");
      if (name === "form-data") return class Form {
        constructor() { this.parts = []; }
        append(...part) { this.parts.push(part); }
        getHeaders() { return { "content-type": "multipart/form-data; boundary=test" }; }
      };
      if (name.startsWith("./")) return require(path.join(__dirname, "../electron", name));
      return require(name);
    },
    __dirname: path.join(__dirname, "../electron"),
    process: { env: { NODE_ENV: "development" }, platform: "win32", arch: "x64" },
    console: { log: (...args) => logs.push(args), error: (...args) => logs.push(args) },
    setTimeout: (callback, delay) => { const id = ++timerId; timers.set(id, { callback, delay, repeat: false }); return id; },
    setInterval: (callback, delay) => { const id = ++timerId; timers.set(id, { callback, delay, repeat: true }); return id; },
    clearTimeout: (id) => timers.delete(id),
    clearInterval: (id) => timers.delete(id),
    URL, Date: ClockDate,
  }, { filename: "electron/main.js" });
  await Promise.resolve();
  return {
    call: (name, ...args) => handlers.get(`agent:${name}`)(null, ...args),
    session: () => {
      const raw = files.get(norm("/agent/session.json"));
      const s = raw ? JSON.parse(raw) : {};
      const enc = files.get(norm("/agent/session-token.enc"));
      return { ...s, token: enc ? Buffer.from(enc, "base64").toString() : "" };
    },
    queue: () => JSON.parse(files.get(norm("/agent/offline-queue.json")) || "[]"),
    inputReport: () => JSON.parse(files.get(norm("/agent/input-diagnostics.json")) || "{}"),
    screenshotReport: () => JSON.parse(files.get(norm("/agent/screenshot-diagnostics.json")) || "{}"),
    screenshotTick: async (startup = false) => {
      const delay = startup ? 10000 : 300000;
      const callbacks = [...timers.entries()].filter(([, t]) => t.delay === delay);
      for (const [id, timer] of callbacks) if (!timer.repeat) timers.delete(id);
      return Promise.all(callbacks.map(([, timer]) => timer.callback()));
    },
    tempScreenshots: () => [...files.keys()].filter(name => name.startsWith(norm("/tmp/workpulse-"))),
    tick: async (milliseconds = 60000) => {
      clock.value += milliseconds;
      return Promise.all([...timers.values()].filter((t) => t.repeat && t.delay === 60000).map((t) => t.callback()));
    },
    advance: (milliseconds) => { clock.value += milliseconds; },
    requests, events, hook, powerMonitor, application, windows, timers, logs,
  };
}

module.exports = { agent };
