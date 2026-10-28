const http = require("node:http");
const crypto = require("node:crypto");

// Runs only in Electron main. The renderer never receives the PKCE verifier.
function createCRMLogin({ post, openExternal, timeoutMs = 300000 }) {
  let pending = null;
  function cancel() {
    pending?.(new Error("CRM login cancelled."));
  }
  async function login(provider) {
    if (pending) throw new Error("A CRM login is already in progress.");
    const state = crypto.randomBytes(32).toString("base64url");
    const verifier = crypto.randomBytes(32).toString("base64url");
    const challenge = crypto
      .createHash("sha256")
      .update(verifier)
      .digest("base64url");
    let server,
      timer,
      finish,
      attempt,
      issuer,
      consumed = false;
    const callback = new Promise((resolve, reject) => {
      finish = (error) => {
        clearTimeout(timer);
        server?.close();
        if (pending === finish) pending = null;
        if (error) reject(error);
      };
      pending = finish;
      server = http.createServer((req, res) => {
        res.setHeader("Cache-Control", "no-store");
        res.setHeader(
          "Content-Security-Policy",
          "default-src 'none'; frame-ancestors 'none'",
        );
        res.setHeader("Referrer-Policy", "no-referrer");
        res.setHeader("Content-Type", "text/plain; charset=utf-8");
        const url = new URL(req.url, "http://127.0.0.1");
        if (
          req.method !== "GET" ||
          url.pathname !== "/crm/callback" ||
          req.headers.host !== `127.0.0.1:${server.address()?.port}`
        ) {
          res.writeHead(404);
          res.end("Not found");
          return;
        }
        if (
          url.searchParams.getAll("state").length !== 1 ||
          url.searchParams.get("state") !== state ||
          consumed ||
          !attempt
        ) {
          res.writeHead(400);
          res.end("Invalid login callback. Return to WorkPulse.");
          return;
        }
        if (
          url.searchParams.getAll("iss").length !== 1 ||
          url.searchParams.get("iss") !== issuer
        ) {
          res.writeHead(400);
          res.end("Invalid CRM issuer.");
          return;
        }
        if (url.searchParams.has("error")) {
          consumed = true;
          res.end("CRM login was cancelled or denied. Return to WorkPulse.");
          finish(new Error("CRM login was cancelled or denied."));
          return;
        }
        const code = url.searchParams.get("code");
        if (
          url.searchParams.getAll("code").length !== 1 ||
          !code ||
          code.length > 2048
        ) {
          res.writeHead(400);
          res.end("Invalid authorization code.");
          return;
        }
        consumed = true;
        res.end(
          "CRM authorization received. Return to WorkPulse to finish signing in.",
        );
        clearTimeout(timer);
        server.close();
        // Keep pending until the exchange finishes, so cancel/second clicks cannot change identity.
        resolve({ code, attempt_token: attempt, code_verifier: verifier });
      });
      server.requestTimeout = 10000;
      server.headersTimeout = 10000;
      server.on("error", finish);
      timer = setTimeout(
        () => finish(new Error("CRM login timed out. Try again.")),
        timeoutMs,
      );
    });
    // Install the rejection handler immediately, including during startup/network failures.
    callback.catch(() => {});
    try {
      await new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", resolve);
      });
      const redirect_uri = `http://127.0.0.1:${server.address().port}/crm/callback`;
      const start = await post("/auth/crm/start/", {
        provider,
        redirect_uri,
        state,
        code_challenge: challenge,
      });
      if (pending !== finish) throw new Error("CRM login cancelled.");
      const auth = new URL(start.authorization_url);
      const localAuth =
        auth.protocol === "http:" &&
        ["127.0.0.1", "localhost"].includes(auth.hostname);
      if (
        (auth.protocol !== "https:" && !localAuth) ||
        auth.username ||
        auth.password ||
        !start.attempt_token ||
        !start.issuer
      )
        throw new Error("Invalid CRM authorization configuration.");
      attempt = start.attempt_token;
      issuer = start.issuer;
      await openExternal(auth.toString());
      const payload = await callback;
      if (pending !== finish) throw new Error("CRM login cancelled.");
      const result = await post("/auth/crm/exchange/", payload);
      if (pending !== finish) throw new Error("CRM login cancelled.");
      return result;
    } finally {
      finish();
    }
  }
  return {
    login,
    cancel,
    get active() {
      return !!pending;
    },
  };
}
module.exports = { createCRMLogin };
