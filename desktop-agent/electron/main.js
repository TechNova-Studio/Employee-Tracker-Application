const {
  app,
  BrowserWindow,
  ipcMain,
  dialog,
  powerMonitor,
  shell,
  safeStorage,
} = require("electron");
const path = require("path");
const fs = require("fs");
const os = require("os");
const crypto = require("crypto");
const axios = require("axios");
const { createCRMLogin } = require("./crm-login");
const { createSessionStore } = require("./session-store");
const { createInputMonitor } = require("./input-monitor");
const { inputReport } = require("./input-report");
let sessionStore;
function secureSessionStore() {
  if (!sessionStore)
    sessionStore = createSessionStore({
      fs,
      directory: app.getPath("userData"),
      safeStorage,
    });
  return sessionStore;
}
let activeWin = null;
let screenshot = null;
let screenshotModuleError = null;
try {
  activeWin = require("active-win");
} catch (e) {
  console.log("active-win unavailable", e.message);
}
try {
  screenshot = require("screenshot-desktop");
} catch (e) {
  screenshotModuleError = { code: e.code || "SCREENSHOT_MODULE_UNAVAILABLE", message: e.message };
  console.log("screenshot-desktop unavailable", e.message);
}

function loadEnvFile() {
  const cwd = typeof process?.cwd === "function" ? process.cwd() : __dirname;
  const candidates = [path.join(__dirname, "../.env"), path.join(cwd, ".env")];
  for (const envPath of candidates) {
    if (fs.existsSync(envPath)) {
      try {
        const content = fs.readFileSync(envPath, "utf8");
        for (const line of content.split(/\r?\n/)) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith("#")) continue;
          const eqIdx = trimmed.indexOf("=");
          if (eqIdx !== -1) {
            const key = trimmed.slice(0, eqIdx).trim();
            const val = trimmed
              .slice(eqIdx + 1)
              .trim()
              .replace(/^['"]|['"]$/g, "");
            process.env[key] = val;
          }
        }
      } catch {}
    }
  }
}
loadEnvFile();

const DEFAULT_API_BASE =
  process.env.WORKPULSE_API_BASE ||
  process.env.BASE_URL ||
  "http://localhost:8000/api";
let API_BASE = DEFAULT_API_BASE;

const APP_VERSION = app.getVersion() || "1.0.0";
const PLATFORM = process.platform === "win32" ? "windows" : process.platform;

let mainWindow;
let authToken = "";
let currentUser = null;
let currentCompany = null;
let deviceId = "";
let runningSession = null;
let trackingTimer = null;
let screenshotTimer = null;
let screenshotStartupTimer = null;
let screenshotCapturePromise = null;
let lastScreenshotAttempt = null;
let trackingTickPromise = null;
let startSessionPromise = null;
let agentQuitting = false;
let signingOut = false;
let captureAllowed = false;
const capturePauses = new Set();
let lastHeartbeatAt = Date.now();
let queueSyncPromise = null;
let lastActivityAt = Date.now();
let lastInputAttempt = null;
const inputMonitor = createInputMonitor({
  onActivity: () => { lastActivityAt = Date.now(); },
  onError: () => writeInputDiagnostics("native_error"),
});
let screenshotIntervalSeconds = 300;
let idleThresholdSeconds = 300;

function userDataFile(name) {
  return path.join(app.getPath("userData"), name);
}
function getInputDiagnostics(event = "status") {
  return inputReport({
    event, version: APP_VERSION, platform: PLATFORM, arch: process.arch,
    running: Boolean(runningSession), capture: inputMonitor.status(),
    attempt: lastInputAttempt,
  });
}
function writeInputDiagnostics(event, attempt) {
  if (attempt) lastInputAttempt = { ...attempt, at: new Date().toISOString() };
  const report = getInputDiagnostics(event);
  // A single overwritten support snapshot, not a history of employee input.
  try { fs.writeFileSync(userDataFile("input-diagnostics.json"), JSON.stringify(report, null, 2)); } catch { /* Disk diagnostics are best effort. */ }
  if (event === "native_error" || event === "upload_count_mismatch" || process.env.WORKPULSE_INPUT_DEBUG === "True")
    console.log("[WorkPulse input]", JSON.stringify(report));
}
function screenshotDiagnostics() {
  return { app_version: APP_VERSION, platform: PLATFORM, session_running: Boolean(runningSession),
    capture_allowed: captureAllowed && !capturePauses.size,
    module_available: Boolean(screenshot), last_attempt: lastScreenshotAttempt };
}
function recordScreenshotAttempt(state, phase, error) {
  const status = error?.status || error?.response?.status;
  const detail = error?.data?.detail || error?.response?.data?.detail || error?.message || "";
  lastScreenshotAttempt = { at: new Date().toISOString(), state, phase,
    http_status: Number.isInteger(status) ? status : null,
    error_code: typeof error?.code === "string" ? error.code.slice(0, 100) : "",
    detail: typeof detail === "string" ? detail.split(/\r?\n/)[0].slice(0, 500) : "" };
  try { fs.writeFileSync(userDataFile("screenshot-diagnostics.json"), JSON.stringify(screenshotDiagnostics(), null, 2)); } catch { /* Best effort support metadata. */ }
  if (state === "failed") console.error("[WorkPulse screenshot]", JSON.stringify(lastScreenshotAttempt));
}
function loadJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function saveJson(file, data) {
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}
function normalizeApiBase(value) {
  let url;
  try {
    url = new URL(String(value || "").trim());
  } catch {
    throw new Error(
      "Enter a full server URL, for example http://127.0.0.1:8000/api.",
    );
  }
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error(
      "Use an HTTP or HTTPS server URL without credentials, query or fragment.",
    );
  const pathname = url.pathname.replace(/\/+$/, "");
  url.pathname = pathname.endsWith("/api") ? pathname : `${pathname}/api`;
  return url.toString().replace(/\/$/, "");
}
function loadApiBase() {
  loadEnvFile();
  const envUrl = process.env.WORKPULSE_API_BASE || process.env.BASE_URL;
  if (envUrl) {
    try {
      API_BASE = normalizeApiBase(envUrl);
      return;
    } catch {}
  }
  const saved = loadJson(userDataFile("server.json"), {});
  if (saved.apiBase) {
    try {
      API_BASE = normalizeApiBase(saved.apiBase);
      return;
    } catch {}
  }
  API_BASE = DEFAULT_API_BASE;
}
function queueOwner() {
  if (!currentUser?.id || !currentCompany?.id) return "";
  return `${API_BASE}:${currentCompany.id}:${currentUser.id}`;
}
function clearLocalSession() {
  stopLocalCapture();
  inputMonitor.reset();
  authToken = "";
  currentUser = null;
  currentCompany = null;
  runningSession = null;
  lastInputAttempt = null;
  lastScreenshotAttempt = null;
  saveSession();
  writeInputDiagnostics("reset");
  try { fs.unlinkSync(userDataFile("screenshot-diagnostics.json")); } catch { /* No prior screenshot diagnostic. */ }
}
function sessionExpired() {
  if (!authToken) return;
  clearLocalSession();
  mainWindow?.webContents.send("agent:authExpired");
}
function queueFile() {
  return userDataFile("offline-queue.json");
}
function getQueue() {
  return loadJson(queueFile(), []);
}
function saveQueue(q) {
  saveJson(queueFile(), q);
}
function getDeviceId() {
  const f = userDataFile("device-id.txt");
  if (fs.existsSync(f)) return fs.readFileSync(f, "utf8");
  const id = crypto.randomUUID();
  fs.writeFileSync(f, id);
  return id;
}
function localIp() {
  const nets = os.networkInterfaces();
  for (const name of Object.keys(nets))
    for (const net of nets[name])
      if (net.family === "IPv4" && !net.internal) return net.address;
  return "";
}
function apiHeaders(extra = {}) {
  return {
    ...extra,
    Authorization: authToken ? `Token ${authToken}` : undefined,
  };
}
function friendlyAxiosError(e) {
  const data = e?.response?.data || {};
  const message =
    e?.response?.status === 401
      ? "Session expired. Sign in again."
      : data.detail ||
        data.reason ||
        data.blocked_reason ||
        (!e?.response
          ? `Cannot reach WorkPulse server at ${API_BASE}. Check the server URL and backend.`
          : e.message) ||
        "API error";
  const err = new Error(message);
  err.data = data;
  err.status = e?.response?.status;
  return err;
}
async function apiGet(url) {
  try {
    return (
      await axios.get(`${API_BASE}${url}`, {
        headers: apiHeaders(),
        timeout: 15000,
      })
    ).data;
  } catch (e) {
    if (e?.response?.status === 401) sessionExpired();
    throw friendlyAxiosError(e);
  }
}
async function apiPost(url, body, headers = {}) {
  try {
    return (
      await axios.post(`${API_BASE}${url}`, body, {
        headers: apiHeaders(headers),
        timeout: 15000,
      })
    ).data;
  } catch (e) {
    if (e?.response?.status === 401) sessionExpired();
    throw friendlyAxiosError(e);
  }
}
function rememberSession(data) {
  secureSessionStore().save(data);
}
function loadSession() {
  const s = secureSessionStore().load();
  authToken = s.token || "";
  currentUser = s.user || null;
  currentCompany = s.company || null;
  deviceId = s.deviceId || getDeviceId();
  runningSession = s.runningSession || null;
  screenshotIntervalSeconds = s.screenshotIntervalSeconds || 300;
  idleThresholdSeconds = s.idleThresholdSeconds || 300;
  // Attribute legacy offline records only while the original saved login
  // still identifies the user and company that created them.
  if (queueOwner()) {
    const queue = getQueue();
    if (queue.some((item) => !item.owner))
      saveQueue(
        queue.map((item) =>
          item.owner ? item : { ...item, owner: queueOwner() },
        ),
      );
  }
}
function saveSession() {
  rememberSession({
    token: authToken,
    user: currentUser,
    company: currentCompany,
    deviceId,
    runningSession,
    screenshotIntervalSeconds,
    idleThresholdSeconds,
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 980,
    height: 720,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  if (!app.isPackaged && process.env.NODE_ENV === "development")
    mainWindow.loadURL("http://localhost:5173");
  else mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  mainWindow.on("close", async (event) => {
    if (runningSession) {
      event.preventDefault();
      const res = await dialog.showMessageBox(mainWindow, {
        type: "warning",
        buttons: ["Stop Session & Quit", "Cancel"],
        message: "Work session is running",
        detail: "Closing will stop tracking and save the session.",
      });
      if (res.response === 0) {
        await stopTracking();
        runningSession = null;
        mainWindow.destroy();
      }
    }
  });
  mainWindow.on("closed", () => crmLogin.cancel());
}

app.whenReady().then(() => {
  loadApiBase();
  loadSession();
  deviceId = getDeviceId();
  createWindow();
  powerMonitor.on?.("lock-screen", () => pauseInputCapture("locked"));
  powerMonitor.on?.("unlock-screen", () => resumeInputCapture("locked"));
  powerMonitor.on?.("suspend", () => pauseInputCapture("suspended"));
  powerMonitor.on?.("resume", () => resumeInputCapture("suspended"));
  // A saved session is not live after a process restart. Send its stop only
  // after the saved login has been verified with the server.
  if (runningSession) {
    enqueue({
      type: "session_stop",
      payload: { session_id: runningSession.id, device_id: deviceId },
    });
    runningSession = null;
    saveSession();
  }
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("agent:getConfig", () => ({
  API_BASE,
  serverUrlLocked: !!(process.env.WORKPULSE_API_BASE || process.env.BASE_URL),
  secureSessionPersistent: secureSessionStore().persistent(),
  APP_VERSION,
  PLATFORM,
  deviceId,
  currentUser,
  currentCompany,
  runningSession,
  screenshotIntervalSeconds,
  idleThresholdSeconds,
}));
ipcMain.handle("agent:setApiBase", (_, value) => {
  if (process.env.WORKPULSE_API_BASE || process.env.BASE_URL)
    throw new Error("Server URL is locked by environment configuration.");
  if (authToken || runningSession || crmLogin.active)
    throw new Error("Sign out before changing the server URL.");
  const trimmed = String(value || "").trim();
  if (!trimmed) {
    saveJson(userDataFile("server.json"), {});
    API_BASE = DEFAULT_API_BASE;
    return API_BASE;
  }
  const normalized = normalizeApiBase(trimmed);
  saveJson(userDataFile("server.json"), { apiBase: normalized });
  API_BASE = normalized;
  return API_BASE;
});
ipcMain.handle("agent:testConnection", async () => {
  try {
    const response = await axios.get(`${API_BASE}/health/`, { timeout: 8000 });
    if (response.data?.product !== "BOLD WorkPulse")
      throw new Error("This URL does not point to a BOLD WorkPulse backend.");
    return { connected: true };
  } catch (e) {
    if (!e.response && e.message?.startsWith("This URL")) throw e;
    throw friendlyAxiosError(e);
  }
});
ipcMain.handle("agent:verifySession", async () => {
  if (!authToken || !currentUser) {
    clearLocalSession();
    return { expired: true };
  }
  try {
    const data = await apiGet("/auth/me/");
    if (!data.company) {
      clearLocalSession();
      return {
        expired: true,
        detail: "Desktop login requires a user assigned to a company.",
      };
    }
    currentUser = data.user;
    currentCompany = data.company;
    saveSession();
    if (getQueue().length) syncQueue().catch(() => {});
    return { expired: false };
  } catch (e) {
    if (e.status === 401) return { expired: true, detail: e.message };
    throw e;
  }
});
ipcMain.handle("agent:versionCheck", async () =>
  apiGet(`/agent/version-check/?platform=${PLATFORM}&version=${APP_VERSION}`),
);
ipcMain.handle("agent:openDownload", async (_, url) => {
  const parsed = new URL(url);
  if (!["https:", "http:"].includes(parsed.protocol))
    throw new Error("Installer URL must use HTTP or HTTPS.");
  await shell.openExternal(parsed.toString());
  return true;
});
ipcMain.handle("agent:login", async (_, payload) => {
  if (crmLogin.active || authToken)
    throw new Error("A login is already in progress or signed in.");
  const email = String(payload?.email || "").trim();
  const password = String(payload?.password || "");
  if (!email || !password) throw new Error("Enter your email and password.");
  let data;
  try {
    data = await axios
      .post(
        `${API_BASE}/auth/login/`,
        { email, password, app_version: APP_VERSION, platform: PLATFORM },
        { timeout: 15000 },
      )
      .then((r) => r.data);
  } catch (e) {
    if (e.response?.data?.blocked_reason === "OUTDATED_AGENT")
      return { blocked: true, version: e.response.data.version };
    throw friendlyAxiosError(e);
  }
  return finishLogin(data);
});

async function finishLogin(data) {
  if (!data.token || !data.user || !data.company)
    throw new Error(
      "Your account has no company assigned. Contact your administrator.",
    );
  authToken = data.token;
  currentUser = data.user;
  currentCompany = data.company;
  screenshotIntervalSeconds = data.screenshot_interval_seconds || 300;
  idleThresholdSeconds = data.idle_threshold_seconds || 300;
  deviceId = getDeviceId();
  try {
    await registerDevice();
    saveSession();
  } catch (e) {
    clearLocalSession();
    if (e.data?.blocked_reason === "OUTDATED_AGENT")
      return { blocked: true, version: e.data.version };
    throw e;
  }
  if (getQueue().length) syncQueue().catch(() => {});
  return data;
}
const crmLogin = createCRMLogin({
  openExternal: (url) => shell.openExternal(url),
  post: async (url, body) => {
    try {
      return (
        await axios.post(
          `${API_BASE}${url}`,
          {
            ...body,
            app_version: APP_VERSION,
            platform: PLATFORM,
          },
          { timeout: 25000 },
        )
      ).data;
    } catch (e) {
      throw friendlyAxiosError(e);
    }
  },
});
app.on("before-quit", () => crmLogin.cancel());
app.on("will-quit", () => {
  agentQuitting = true;
  stopLocalCapture();
  crmLogin.cancel();
});
ipcMain.handle("agent:crmProviders", async () => {
  try {
    return (
      await axios.get(`${API_BASE}/auth/crm/providers/`, { timeout: 10000 })
    ).data;
  } catch (e) {
    throw friendlyAxiosError(e);
  }
});
ipcMain.handle("agent:crmLogin", async (_, provider) => {
  if (authToken || runningSession)
    throw new Error("Sign out before starting CRM login.");
  const server = new URL(API_BASE);
  if (
    server.protocol !== "https:" &&
    !["127.0.0.1", "localhost", "[::1]"].includes(server.hostname)
  )
    throw new Error("CRM login requires HTTPS for the WorkPulse server.");
  try {
    return await finishLogin(await crmLogin.login(String(provider || "")));
  } catch (e) {
    if (e.data?.blocked_reason === "OUTDATED_AGENT")
      return { blocked: true, version: e.data.version };
    throw e;
  }
});
ipcMain.handle("agent:cancelCRMLogin", () => {
  crmLogin.cancel();
  return true;
});
ipcMain.handle("agent:registerDevice", () => registerDevice());
ipcMain.handle("agent:getPolicy", async () => {
  try {
    return await apiGet("/policy/current/");
  } catch (e) {
    if (e.status === 404)
      return { policy: null, accepted: false, missing: true };
    throw e;
  }
});
ipcMain.handle("agent:acceptPolicy", async (_, policyId) =>
  apiPost("/policy/accept/", { device_id: deviceId, policy_id: policyId }),
);

ipcMain.handle("agent:declinePolicy", async (_, policyId) =>
  apiPost("/policy/decline/", { device_id: deviceId, policy_id: policyId }),
);
ipcMain.handle("agent:startSession", () => {
  if (startSessionPromise) return startSessionPromise;
  startSessionPromise = beginSession().finally(() => { startSessionPromise = null; });
  return startSessionPromise;
});
async function beginSession() {
  if (signingOut) throw new Error("Wait for sign-out to finish before starting a work session.");
  if (runningSession) return runningSession;
  const startingToken = authToken;
  const startingOwner = queueOwner();
  if (!startingToken) throw new Error("Sign in before starting a work session.");
  try {
    await syncQueue();
    const data = await apiPost("/agent/session/start/", {
      device_id: deviceId,
      app_version: APP_VERSION,
      platform: PLATFORM,
    });
    if (authToken !== startingToken || agentQuitting || signingOut) {
      // A sign-out can finish while the start request is still in flight.
      // Never start capture for that late response. Close the accepted server
      // session on the original employee's next authenticated queue sync.
      if (data.id) enqueue({ type: "session_stop", owner: startingOwner,
        payload: { session_id: data.id, device_id: deviceId } });
      throw new Error("The login changed before the work session started. Sign in again.");
    }
    runningSession = data;
    saveSession();
    startTracking();
    return data;
  } catch (e) {
    if (e.data?.blocked_reason === "OUTDATED_AGENT")
      return { blocked: true, version: e.data.version };
    if (
      [
        "POLICY_NOT_ACCEPTED",
        "POLICY_NOT_CONFIGURED",
        "POLICY_DECLINED",
        "EMPLOYEE_INACTIVE",
      ].includes(e.data?.blocked_reason)
    )
      return { blocked: true, reason: e.data.blocked_reason };
    throw e;
  }
}
ipcMain.handle("agent:stopSession", async (_, flush = true) => {
  return stopTracking(flush);
});
ipcMain.handle("agent:status", async () => ({
  runningSession,
  queueLength: getQueue().length,
  deviceId,
  currentUser,
  currentCompany,
  inputCapture: inputMonitor.status(),
}));
// Developer/support inspection only. No counters are displayed in the agent UI.
ipcMain.handle("agent:inputDiagnostics", () => getInputDiagnostics());
ipcMain.handle("agent:screenshotDiagnostics", () => screenshotDiagnostics());
ipcMain.handle("agent:syncNow", async () => syncQueue());
ipcMain.handle("agent:logout", async () => {
  signingOut = true;
  stopLocalCapture();
  try {
    if (runningSession) await stopTracking();
    try { await apiPost("/auth/logout/", {}); } catch { /* Local sign-out still completes. */ }
  } finally {
    clearLocalSession();
    signingOut = false;
  }
  return { success: true };
});

async function registerDevice() {
  return apiPost("/agent/device/register/", {
    device_id: deviceId,
    hostname: os.hostname(),
    platform: PLATFORM,
    local_ip: localIp(),
    app_version: APP_VERSION,
  });
}
function startTracking() {
  stopLocalCapture();
  inputMonitor.reset();
  lastHeartbeatAt = Date.now();
  lastActivityAt = Date.now();
  lastInputAttempt = null;
  lastScreenshotAttempt = null;
  captureAllowed = true;
  if (capturePauses.size) inputMonitor.pause();
  else inputMonitor.start();
  writeInputDiagnostics("capture_started");
  trackingTimer = setInterval(() => trackOnce().catch(() => {}), 60000);
  screenshotTimer = setInterval(
    captureScreenshot,
    Math.max(60, screenshotIntervalSeconds) * 1000,
  );
  screenshotStartupTimer = setTimeout(captureScreenshot, 10000);
}
function stopLocalCapture() {
  captureAllowed = false;
  clearInterval(trackingTimer);
  clearInterval(screenshotTimer);
  clearTimeout(screenshotStartupTimer);
  inputMonitor.stop();
  writeInputDiagnostics("capture_stopped");
}
function pauseInputCapture(reason) {
  capturePauses.add(reason);
  if (runningSession) {
    inputMonitor.pause();
    writeInputDiagnostics("capture_paused");
  }
}
function resumeInputCapture(reason) {
  capturePauses.delete(reason);
  if (captureAllowed && runningSession && authToken && !agentQuitting && !signingOut && !capturePauses.size) {
    inputMonitor.start();
    writeInputDiagnostics("capture_resumed");
  }
}
async function stopTracking(flush = true) {
  // Stop the OS listener before any upload or logout request can wait on the
  // network. Preserve already-counted input for the final activity batch.
  stopLocalCapture();
  if (!runningSession) return { status: "NO_RUNNING_SESSION" };
  const stoppingSessionId = runningSession.id;
  if (flush) {
    // A timer tick may already be sending. Let it finish, then flush input that
    // arrived since its snapshot; do not run overlapping activity uploads.
    if (trackingTickPromise) await trackingTickPromise;
    if (runningSession?.id === stoppingSessionId) await trackOnce();
  }
  if (!runningSession) return { status: "AUTO_STOPPED" };
  if (runningSession.id !== stoppingSessionId) return { status: "SESSION_CHANGED" };
  const sessionId = runningSession.id;
  runningSession = null;
  saveSession();
  writeInputDiagnostics("session_stopped");
  await syncQueue();
  try {
    return await apiPost("/agent/session/stop/", {
      session_id: sessionId,
      device_id: deviceId,
      app_version: APP_VERSION,
      platform: PLATFORM,
    });
  } catch (e) {
    if (e.status === 404) return { status: "ALREADY_STOPPED" };
    enqueue({
      type: "session_stop",
      payload: { session_id: sessionId, device_id: deviceId },
    });
    return { queued: true };
  }
}

async function handleOutdatedAgent(error) {
  const details = error.data || error.response?.data;
  if (details?.blocked_reason !== "OUTDATED_AGENT") return false;
  if (runningSession) await stopTracking(false);
  mainWindow?.webContents.send("agent:updateRequired", details.version);
  return true;
}

async function handlePolicyGate(error) {
  const details = error.data || error.response?.data;
  if (
    ![
      "POLICY_NOT_ACCEPTED",
      "POLICY_NOT_CONFIGURED",
      "POLICY_DECLINED",
      "EMPLOYEE_INACTIVE",
    ].includes(details?.blocked_reason)
  )
    return false;
  if (runningSession) await stopTracking(false);
  mainWindow?.webContents.send("agent:policyRequired", details.blocked_reason);
  return true;
}

async function handleEndedSession(error) {
  const details = error.data || error.response?.data;
  const companyBlocked = ["TRIAL_EXPIRED", "SUSPENDED"].includes(
    details?.blocked_reason,
  );
  if (
    !companyBlocked &&
    ((error.status || error.response?.status) !== 404 ||
      details?.detail !== "Running session not found")
  )
    return false;
  if (runningSession) await stopTracking(false);
  mainWindow?.webContents.send(
    "agent:sessionEnded",
    companyBlocked ? details.detail : undefined,
  );
  return true;
}

function enqueue(item) {
  const q = getQueue();
  q.push({ ...item, owner: item.owner || queueOwner(), queued_at: new Date().toISOString() });
  saveQueue(q);
}
function trackOnce() {
  if (trackingTickPromise) return trackingTickPromise;
  trackingTickPromise = trackCurrentInterval().finally(() => { trackingTickPromise = null; });
  return trackingTickPromise;
}
async function trackCurrentInterval() {
  if (!runningSession) return;
  const sessionId = runningSession.id;
  const token = authToken;
  const elapsedSeconds = Math.min(
    60,
    Math.max(0, Math.floor((Date.now() - lastHeartbeatAt) / 1000)),
  );
  lastHeartbeatAt = Date.now();
  // Snapshot before awaiting window/network work. New events belong to the
  // next interval; draining never resets the employee's session totals.
  const counts = inputMonitor.drain();
  if (!elapsedSeconds && !counts.keyboard_count && !counts.mouse_count) return;
  // System-wide idle time. This uses Electron powerMonitor and is not limited to mouse/keyboard activity inside the WorkPulse window.
  let idleSeconds = 0;
  try {
    idleSeconds = powerMonitor.getSystemIdleTime();
  } catch {
    idleSeconds = Math.floor((Date.now() - lastActivityAt) / 1000);
  }
  const isIdle = idleSeconds >= idleThresholdSeconds;
  let win = { owner: { name: "Unknown" }, title: "Unknown" };
  try {
    if (activeWin) win = await activeWin();
  } catch {}
  if (!runningSession || runningSession.id !== sessionId || authToken !== token) return;
  const activity = {
    app_name: win?.owner?.name || "Unknown",
    window_title: win?.title || "",
    domain: extractDomain(win?.title || ""),
    duration_seconds: elapsedSeconds,
    mouse_count: counts.mouse_count,
    keyboard_count: counts.keyboard_count,
  };
  const heartbeat = {
    session_id: sessionId,
    device_id: deviceId,
    active_seconds: isIdle ? 0 : elapsedSeconds,
    idle_seconds: isIdle ? Math.min(elapsedSeconds, idleSeconds) : 0,
    is_idle: isIdle,
    app_version: APP_VERSION,
    platform: PLATFORM,
  };
  const activityPayload = {
    session_id: sessionId,
    device_id: deviceId,
    app_version: APP_VERSION,
    platform: PLATFORM,
    activities: [activity],
  };
  writeInputDiagnostics("interval_ready", { outcome: "prepared", ...counts });
  try {
    await apiPost("/agent/heartbeat/", heartbeat);
  } catch (e) {
    if (await handleOutdatedAgent(e)) return;
    if (await handlePolicyGate(e)) return;
    if (await handleEndedSession(e)) return;
    enqueue({ type: "heartbeat", payload: heartbeat });
    enqueue({ type: "activity", payload: activityPayload });
    writeInputDiagnostics("activity_queued", { outcome: "queued_after_heartbeat", http_status: e.status, ...counts });
    return;
  }
  if (!runningSession || runningSession.id !== sessionId) return;
  try {
    const saved = await apiPost("/agent/activity/batch/", activityPayload);
    const row = saved?.items?.[0];
    const comparable = Number.isSafeInteger(row?.keyboard_count) && Number.isSafeInteger(row?.mouse_count);
    const mismatch = comparable && (row.keyboard_count !== counts.keyboard_count || row.mouse_count !== counts.mouse_count);
    writeInputDiagnostics(mismatch ? "upload_count_mismatch" : "activity_uploaded", {
      outcome: mismatch ? "uploaded_count_mismatch" : "uploaded", ...counts,
      server_keyboard_count: row?.keyboard_count, server_mouse_count: row?.mouse_count,
    });
  } catch (e) {
    if (await handleOutdatedAgent(e)) return;
    if (await handlePolicyGate(e)) return;
    if (await handleEndedSession(e)) return;
    enqueue({ type: "activity", payload: activityPayload });
    writeInputDiagnostics("activity_queued", { outcome: "queued_after_activity", http_status: e.status, ...counts });
    return;
  }
  await syncQueue();
}
function extractDomain(text) {
  const m = String(text).match(/([a-z0-9-]+\.)+[a-z]{2,}/i);
  return m ? m[0].toLowerCase() : "";
}
function captureScreenshot() {
  if (screenshotCapturePromise) return screenshotCapturePromise;
  screenshotCapturePromise = captureCurrentScreenshot().finally(() => { screenshotCapturePromise = null; });
  return screenshotCapturePromise;
}
function screenshotAllowed(sessionId, token) {
  return Boolean(runningSession && runningSession.id === sessionId && authToken === token &&
    authToken && captureAllowed && !capturePauses.size && !signingOut && !agentQuitting);
}
async function captureCurrentScreenshot() {
  if (!runningSession) return;
  const sessionId = runningSession.id;
  const token = authToken;
  const capturedDeviceId = deviceId;
  if (!screenshotAllowed(sessionId, token)) return;
  if (!screenshot) { recordScreenshotAttempt("failed", "module", screenshotModuleError); return; }
  let tmp;
  let phase = "capture";
  try {
    const img = await screenshot({ format: "png" });
    if (!screenshotAllowed(sessionId, token)) return;
    tmp = path.join(app.getPath("temp"), `workpulse-${crypto.randomUUID()}.png`);
    fs.writeFileSync(tmp, img);
    phase = "upload";
    await uploadScreenshot(tmp, sessionId, token, capturedDeviceId);
    if (authToken === token) recordScreenshotAttempt("uploaded", "upload");
  } catch (e) {
    // An old request must not stop or label a newly signed-in user's session.
    if (authToken !== token || runningSession?.id !== sessionId) return;
    recordScreenshotAttempt("failed", phase, e);
    if ((e.status || e.response?.status) === 401) { sessionExpired(); return; }
    if (await handleOutdatedAgent(e)) return;
    if (await handlePolicyGate(e)) return;
    if (await handleEndedSession(e)) return;
  } finally {
    try { if (tmp && fs.existsSync(tmp)) fs.unlinkSync(tmp); } catch (error) {
      console.error("[WorkPulse screenshot] Temporary capture cleanup failed:", error.code || error.name);
    }
  }
}
async function uploadScreenshot(filePath, sessionId, token, capturedDeviceId) {
  const FormData = require("form-data");
  const form = new FormData();
  form.append("session_id", String(sessionId));
  form.append("device_id", capturedDeviceId);
  form.append("app_version", APP_VERSION);
  form.append("platform", PLATFORM);
  form.append(
    "checksum",
    crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex"),
  );
  form.append("file", fs.createReadStream(filePath));
  return axios.post(`${API_BASE}/agent/screenshots/upload/`, form, {
    headers: { ...form.getHeaders(), Authorization: `Token ${token}` },
    timeout: 60000,
  });
}
async function syncQueue() {
  if (queueSyncPromise) return queueSyncPromise;
  queueSyncPromise = syncQueuedItems().finally(() => {
    queueSyncPromise = null;
  });
  return queueSyncPromise;
}

async function syncQueuedItems() {
  const q = getQueue();
  if (!q.length) return { synced: 0 };
  const remaining = [];
  let synced = 0;
  for (let index = 0; index < q.length; index++) {
    const item = q[index];
    if (!authToken || !queueOwner() || item.owner !== queueOwner()) {
      remaining.push(item);
      continue;
    }
    try {
      if (item.type === "heartbeat")
        await apiPost("/agent/heartbeat/", item.payload);
      else if (item.type === "activity")
        await apiPost("/agent/activity/batch/", item.payload);
      else if (item.type === "session_stop")
        await apiPost("/agent/session/stop/", item.payload);
      synced++;
    } catch (e) {
      if (item.type === "session_stop" && e.status === 404) {
        synced++;
        continue;
      }
      remaining.push(item);
      if (!e.status || [401, 403, 404, 426].includes(e.status)) {
        remaining.push(...q.slice(index + 1));
        break;
      }
    }
  }
  saveQueue(remaining);
  return { synced, remaining: remaining.length };
}
