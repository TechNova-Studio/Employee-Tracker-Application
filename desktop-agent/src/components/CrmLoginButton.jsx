import React, { useState, useEffect } from "react";

export function CrmLoginButton({ onCrmLogin, busy, apiBase }) {
  const [crmProviders, setCRMProviders] = useState([]);
  const [crmProvider, setCRMProvider] = useState("");
  const [crmPending, setCRMPending] = useState(false);
  const [crmError, setCRMError] = useState("");

  useEffect(() => {
    let live = true;
    setCRMProviders([]);
    setCRMError("");

    if (window.workpulse?.crmProviders) {
      window.workpulse
        .crmProviders()
        .then((data) => {
          if (live) {
            const list = data?.providers || [];
            setCRMProviders(list);
            if (list.length > 0) {
              setCRMProvider(list[0].id || "");
            }
          }
        })
        .catch(() => {
          if (live) {
            setCRMError(
              "CRM login is unavailable. Check server settings or contact your administrator."
            );
          }
        });
    }

    return () => {
      live = false;
    };
  }, [apiBase]);

  async function handleLogin() {
    if (busy || crmPending) return;
    setCRMError("");
    setCRMPending(true);
    try {
      await onCrmLogin(crmProvider);
    } catch (err) {
      setCRMError(err.message || "CRM login failed");
    } finally {
      setCRMPending(false);
    }
  }

  async function handleCancel() {
    try {
      await window.workpulse?.cancelCRMLogin();
    } catch {}
    setCRMPending(false);
  }

  if (crmProviders.length === 0 && !crmError) {
    return null;
  }

  return (
    <div className="crm-section">
      {crmProviders.length > 1 && (
        <div className="form-group">
          <label htmlFor="crm-provider-select">CRM Company</label>
          <select
            id="crm-provider-select"
            className="form-control"
            value={crmProvider}
            disabled={busy || crmPending}
            onChange={(e) => setCRMProvider(e.target.value)}
          >
            {crmProviders.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {crmProviders.length > 0 && (
        <button
          type="button"
          className="btn-crm"
          disabled={busy || crmPending}
          onClick={handleLogin}
        >
          {crmPending ? "Waiting for CRM login..." : "Login with CRM"}
        </button>
      )}

      {crmPending && (
        <div className="crm-pending-box">
          <p>Complete CRM login in your browser.</p>
          <button
            type="button"
            className="btn-secondary"
            style={{ padding: "6px 14px", fontSize: "12px", width: "auto" }}
            onClick={handleCancel}
          >
            Cancel CRM login
          </button>
        </div>
      )}

      {crmError && (
        <p className="field-hint" style={{ color: "var(--danger)", marginTop: "6px" }} role="status">
          {crmError}
        </p>
      )}

      <div className="crm-divider">or sign in with password</div>
    </div>
  );
}

export default CrmLoginButton;
