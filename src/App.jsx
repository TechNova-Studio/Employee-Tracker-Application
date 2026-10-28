import React, { useState, useEffect } from "react";
import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { LoginScreen } from "./screens/LoginScreen";
import { DashboardScreen } from "./screens/DashboardScreen";
import { PolicyScreen } from "./screens/PolicyScreen";
import { UpdateScreen } from "./screens/UpdateScreen";
import { StatusScreen } from "./screens/StatusScreen";

export default function App() {
  const [screen, setScreen] = useState("loading");
  const [cfg, setCfg] = useState({});
  const [version, setVersion] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [status, setStatus] = useState({});
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [lastSession, setLastSession] = useState(() => {
    try {
      const saved = localStorage.getItem("workpulse_last_session");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  // Setup listeners for Electron background signals
  useEffect(() => {
    const removeAuth = window.workpulse.onAuthExpired(() => {
      setScreen("login");
      setStatus({});
      setPolicy(null);
      setMessage({ type: "error", text: "Session expired. Please sign in again." });
      window.workpulse.getConfig().then(setCfg).catch(() => {});
    });

    const removeUpdate = window.workpulse.onUpdateRequired((v) => {
      setVersion(v);
      setScreen("update");
    });

    const removePolicy = window.workpulse.onPolicyRequired(() => {
      refreshPolicy().catch((err) => setMessage({ type: "error", text: err.message }));
    });

    const removeEnded = window.workpulse.onSessionEnded((msg) => {
      window.workpulse.status().then(setStatus);
      setMessage({
        type: "info",
        text: msg || "Session ended on the server. Start a new work session to continue.",
      });
    });

    init();
    return () => {
      removeAuth();
      removeUpdate();
      removePolicy();
      removeEnded();
    };
  }, []);

  // Refresh local attendance/queue state without a backend API request.
  useEffect(() => {
    if (screen !== "dashboard") return;
    const interval = setInterval(() => {
      window.workpulse
        .status()
        .then(setStatus)
        .catch(() => {});
    }, 20000);
    return () => clearInterval(interval);
  }, [screen]);

  async function refreshPolicy() {
    const p = await window.workpulse.getPolicy();
    setPolicy(p);
    if (["POLICY_DECLINED", "EMPLOYEE_INACTIVE"].includes(p.blocked_reason)) {
      setScreen("declined");
    } else if (p.missing) {
      setScreen("policy-missing");
    } else if (p.accepted) {
      setStatus(await window.workpulse.status());
      setScreen("dashboard");
    } else {
      setScreen("policy");
    }
  }

  async function init() {
    setScreen("loading");
    try {
      const c = await window.workpulse.getConfig();
      setCfg(c);
      if (c.currentUser) {
        const verified = await window.workpulse.verifySession();
        if (verified.expired) {
          setCfg(await window.workpulse.getConfig());
          setMessage({
            type: "error",
            text: verified.detail || "Session expired. Please sign in again.",
          });
          setScreen("login");
          return;
        }
        setCfg(await window.workpulse.getConfig());
        const v = await window.workpulse.versionCheck();
        setVersion(v);
        if (v.force_update_required) {
          setScreen("update");
        } else {
          await refreshPolicy();
        }
      } else {
        try {
          setVersion(await window.workpulse.versionCheck());
        } catch (err) {
          setMessage({ type: "error", text: err.message });
        }
        setScreen("login");
      }
    } catch (err) {
      setMessage({ type: "error", text: err.message });
      const current = await window.workpulse.getConfig().catch(() => cfg);
      setCfg(current);
      setScreen(current.currentUser ? "connection" : "login");
    }
  }

  async function handleLogin(credentials) {
    if (busy) return;
    setMessage(null);
    setBusy(true);
    let signedIn = false;
    try {
      const data = await window.workpulse.login(credentials);
      if (data.blocked) {
        setVersion(data.version);
        setScreen("update");
        return;
      }
      signedIn = true;
      setCfg(await window.workpulse.getConfig());
      setScreen("loading");
      const v = await window.workpulse.versionCheck();
      setVersion(v);
      if (v.force_update_required) {
        setScreen("update");
        return;
      }
      await refreshPolicy();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
      if (signedIn) {
        const current = await window.workpulse.getConfig().catch(() => cfg);
        setCfg(current);
        setScreen(current.currentUser ? "connection" : "login");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleCrmLogin(providerId) {
    if (busy) return;
    setMessage(null);
    setBusy(true);
    let signedIn = false;
    try {
      const data = await window.workpulse.crmLogin(providerId);
      if (data.blocked) {
        setVersion(data.version);
        setScreen("update");
        return;
      }
      signedIn = true;
      setCfg(await window.workpulse.getConfig());
      setScreen("loading");
      const v = await window.workpulse.versionCheck();
      setVersion(v);
      if (v.force_update_required) {
        setScreen("update");
        return;
      }
      await refreshPolicy();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
      if (signedIn) {
        const current = await window.workpulse.getConfig().catch(() => cfg);
        setCfg(current);
        setScreen(current.currentUser ? "connection" : "login");
      }
    } finally {
      setBusy(false);
    }
  }

  function handleLogout() {
    setShowLogoutConfirm(true);
  }

  async function confirmLogout() {
    setShowLogoutConfirm(false);
    // Instantly transition to login screen - zero freeze
    setBusy(false);
    setScreen("login");
    setMessage(null);
    setStatus({});
    setPolicy(null);

    try {
      await window.workpulse.logout();
    } catch (e) {
      // background cleanup handled safely
    } finally {
      setBusy(false);
      const c = await window.workpulse.getConfig().catch(() => ({}));
      setCfg(c);
      if (window.workpulse.focusWindow) {
        window.workpulse.focusWindow().catch(() => {});
      }
    }
  }

  async function handleStartSession() {
    try {
      setMessage(null);
      const s = await window.workpulse.startSession();
      if (s.blocked) {
        if (s.version) {
          setVersion(s.version);
          setScreen("update");
        } else {
          await refreshPolicy();
        }
        return;
      }
      const st = await window.workpulse.status();
      setStatus(st);
      setMessage({ type: "success", text: "Punch-in confirmed. Shift attendance started." });
    } catch (e) {
      setMessage({ type: "error", text: e.message });
    }
  }

  async function handleStopSession() {
    try {
      setMessage(null);
      const stopped = await window.workpulse.stopSession();
      const st = await window.workpulse.status();
      setStatus(st);
      if (stopped && (stopped.id || stopped.stopped_at)) {
        setLastSession(stopped);
        try {
          localStorage.setItem("workpulse_last_session", JSON.stringify(stopped));
        } catch {}
      }
      setMessage({ type: "info", text: "Punch-out recorded. Shift attendance saved." });
    } catch (e) {
      setMessage({ type: "error", text: e.message });
    }
  }

  async function handleSyncNow() {
    if (syncing) return;
    setSyncing(true);
    try {
      const r = await window.workpulse.syncNow();
      const updated = await window.workpulse.status();
      setStatus(updated);
      setMessage({
        type: "success",
        text: `Sync completed (${r.synced || 0} uploaded, ${r.remaining || 0} remaining).`,
      });
    } catch (e) {
      setMessage({ type: "error", text: `Sync failed: ${e.message}` });
    } finally {
      setSyncing(false);
    }
  }

  async function handleAcceptPolicy() {
    try {
      setMessage(null);
      await window.workpulse.acceptPolicy(policy.policy.id);
      await refreshPolicy();
    } catch (e) {
      setMessage({ type: "error", text: e.message });
      if (e.message.includes("Policy changed")) await refreshPolicy();
    }
  }

  async function handleDeclinePolicy() {
    try {
      setMessage(null);
      await window.workpulse.declinePolicy(policy.policy.id);
      await window.workpulse.stopSession(false);
      setStatus(await window.workpulse.status());
      setScreen("declined");
    } catch (e) {
      setMessage({ type: "error", text: e.message });
      if (e.message.includes("Policy changed")) await refreshPolicy();
    }
  }

  async function handleReviewPolicy() {
    try {
      const current = await window.workpulse.getPolicy();
      setPolicy(current);
      setScreen(
        current.blocked_reason
          ? "declined"
          : current.missing
          ? "policy-missing"
          : "policy"
      );
    } catch (e) {
      setMessage({ type: "error", text: e.message });
    }
  }

  const queueLength = status?.queueLength || 0;
  const appVersion = cfg?.APP_VERSION || "1.0.0";

  return (
    <div className="app-layout">
      <Header
        currentUser={cfg?.currentUser}
        currentCompany={cfg?.currentCompany}
        onLogout={handleLogout}
      />

      <main className="app-main">
        {screen === "loading" && <StatusScreen type="loading" />}

        {screen === "connection" && (
          <StatusScreen
            type="connection"
            message={message}
            onClearMessage={() => setMessage(null)}
            onRetry={init}
            onLogout={cfg?.currentUser ? handleLogout : null}
          />
        )}

        {screen === "policy-missing" && (
          <StatusScreen
            type="policy-missing"
            message={message}
            onClearMessage={() => setMessage(null)}
            onRetry={() => refreshPolicy().catch((err) => setMessage({ type: "error", text: err.message }))}
            onLogout={handleLogout}
          />
        )}

        {screen === "declined" && (
          <StatusScreen
            type="declined"
            message={message}
            onClearMessage={() => setMessage(null)}
            onLogout={handleLogout}
          />
        )}

        {screen === "update" && (
          <UpdateScreen
            version={version}
            currentVersion={appVersion}
            message={message}
            onClearMessage={() => setMessage(null)}
            onDownload={(url) =>
              window.workpulse.openDownload(url).catch((err) =>
                setMessage({ type: "error", text: err.message })
              )
            }
            onLogout={handleLogout}
          />
        )}

        {screen === "login" && (
          <LoginScreen
            busy={busy}
            message={message}
            onClearMessage={() => setMessage(null)}
            onLogin={handleLogin}
            onCrmLogin={handleCrmLogin}
            apiBase={cfg?.API_BASE}
          />
        )}

        {screen === "policy" && (
          <PolicyScreen
            policy={policy}
            message={message}
            onClearMessage={() => setMessage(null)}
            onAccept={handleAcceptPolicy}
            onDecline={handleDeclinePolicy}
            onReturnDashboard={() => setScreen("dashboard")}
            onLogout={handleLogout}
          />
        )}

        {screen === "dashboard" && (
          <DashboardScreen
            status={status}
            lastSession={lastSession}
            cfg={cfg}
            message={message}
            onClearMessage={() => setMessage(null)}
            onStartSession={handleStartSession}
            onStopSession={handleStopSession}
            onReviewPolicy={handleReviewPolicy}
          />
        )}
      </main>

      <Footer
        queueLength={queueLength}
        appVersion={appVersion}
        onSync={handleSyncNow}
        syncing={syncing}
      />

      {showLogoutConfirm && (
        <div className="confirm-modal-backdrop" onClick={() => setShowLogoutConfirm(false)}>
          <div className="confirm-modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-modal-header">
              <span className="confirm-icon">⚠️</span>
              <h3>Confirm Sign Out</h3>
            </div>
            <p className="confirm-modal-text">
              Are you sure you want to sign out? Any active tracking session will be stopped immediately.
            </p>
            <div className="confirm-modal-actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowLogoutConfirm(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-danger"
                onClick={confirmLogout}
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
