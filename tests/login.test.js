const test = require("node:test");
const assert = require("node:assert/strict");
const { agent } = require("../test-support/agent");
const BASE = "https://bold-workpulse-staging-45d346b2fac7.herokuapp.com/api";
const user = { id: 7, email: "employee@example.test" };
const company = { id: 1, name: "Tenant" };

test("failed device registration rolls back the desktop login", async () => {
  const desktop = await agent({ post: async (url) => {
    if (url.endsWith("/auth/login/")) return { data: { token: "token-7", user, company } };
    throw { response: { status: 400, data: { detail: "Device registration failed" } } };
  } });
  await assert.rejects(desktop.call("login", { email: " employee@example.test ", password: "pass" }),
    /Device registration failed/);
  assert.equal((await desktop.call("getConfig")).currentUser, null);
  assert.equal(desktop.session().token, "");
  assert.equal(desktop.requests[0][2].email, user.email);
});

test("successful desktop login registers the device and survives a verified restart", async () => {
  const desktop = await agent({ post: async (url) => url.endsWith("/auth/login/")
    ? { data: { token: "token-7", user, company } }
    : { data: { id: 55 } },
  });
  await desktop.call("login", { email: user.email, password: "pass" });
  assert.equal(desktop.session().token, "token-7");
  const registration = desktop.requests.find(([, url]) => url.endsWith("/agent/device/register/"));
  assert.equal(registration[3].headers.Authorization, "Token token-7");
  const restarted = await agent({
    savedSession: desktop.session(),
    get: async () => ({ data: { user, company } }),
  });
  assert.equal((await restarted.call("verifySession")).expired, false);
  assert.equal((await restarted.call("getConfig")).currentUser.id, user.id);
});

test("cached token is verified before queued work is sent, then cleared on 401", async () => {
  const desktop = await agent({
    savedSession: { token: "revoked", user, company, deviceId: "desk-1" },
    savedQueue: [{ type: "session_stop", payload: { session_id: 42, device_id: "desk-1" } }],
    get: async () => { throw { response: { status: 401, data: { detail: "Invalid token" } } }; },
  });
  assert.equal(desktop.requests.length, 0);
  assert.equal((await desktop.call("verifySession")).expired, true);
  assert.equal(desktop.requests.length, 1);
  assert.equal(desktop.requests[0][1], `${BASE}/auth/me/`);
  assert.equal(desktop.session().token, "");
  assert.equal(desktop.queue()[0].owner, `${BASE}:1:7`);
  assert.equal(desktop.events.some(([name]) => name === "agent:authExpired"), true);
});

test("company version block and server change do not save a login", async () => {
  const desktop = await agent({ post: async () => {
    throw { response: { status: 426, data: { blocked_reason: "OUTDATED_AGENT", version: { minimum_supported_version: "2.0.0" } } } };
  } });
  const blocked = await desktop.call("login", { email: user.email, password: "pass" });
  assert.equal(blocked.blocked, true);
  assert.equal((await desktop.call("getConfig")).currentUser, null);
  const url = await desktop.call("setApiBase", "http://192.168.1.5:8000/");
  assert.equal(url, "http://192.168.1.5:8000/api");
  assert.equal((await desktop.call("testConnection")).connected, true);
  assert.throws(() => desktop.call("setApiBase", "file:///tmp/workpulse"), /HTTP or HTTPS/);
});

test("device version rejection clears the partially authenticated session", async () => {
  const desktop = await agent({ post: async (url) => {
    if (url.endsWith("/auth/login/")) return { data: { token: "token-7", user, company } };
    throw { response: { status: 426, data: { blocked_reason: "OUTDATED_AGENT", version: { minimum_supported_version: "2.0.0" } } } };
  } });
  const blocked = await desktop.call("login", { email: user.email, password: "pass" });
  assert.equal(blocked.version.minimum_supported_version, "2.0.0");
  assert.equal(desktop.session().token, "");
  assert.equal((await desktop.call("getConfig")).currentUser, null);
});

test("offline queue never replays under another user's token", async () => {
  const desktop = await agent({
    savedQueue: [{ type: "session_stop", owner: `${BASE}:1:7`, payload: { session_id: 42, device_id: "desk-1" } }],
    post: async (url) => url.endsWith("/auth/login/")
      ? { data: { token: "token-8", user: { id: 8 }, company } }
      : { data: {} },
  });
  await desktop.call("login", { email: "second@example.test", password: "pass" });
  await desktop.call("syncNow");
  assert.equal(desktop.requests.some(([, url]) => url.endsWith("/agent/session/stop/")), false);
  assert.equal(desktop.queue().length, 1);
});
