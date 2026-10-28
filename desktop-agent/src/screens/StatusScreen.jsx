import React from "react";
import { Alert } from "../components/Alert";

export function StatusScreen({
  type,
  message,
  onClearMessage,
  onRetry,
  onLogout,
  apiBase,
}) {
  if (type === "loading") {
    return (
      <div className="center-wrapper">
        <div className="loading-card">
          <div className="loading-spinner" />
          <p>Connecting to BOLD WorkPulse...</p>
        </div>
      </div>
    );
  }

  if (type === "connection") {
    return (
      <div className="center-wrapper">
        <div className="auth-box">
          <div className="auth-brand-header">
            <div className="error-icon-badge">!</div>
            <h2>Server Unavailable</h2>
            <p>Could not connect to the WorkPulse server. Please verify your network connection.</p>
          </div>

          <Alert message={message} onClose={onClearMessage} />

          <div className="button-group-col" style={{ marginTop: "16px" }}>
            <button type="button" className="btn-primary full-width" onClick={onRetry}>
              Retry Connection
            </button>
            {onLogout && (
              <button type="button" className="btn-secondary full-width" onClick={onLogout}>
                Sign Out
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (type === "policy-missing") {
    return (
      <div className="center-wrapper">
        <div className="auth-box">
          <div className="auth-brand-header">
            <div className="warning-icon-badge">!</div>
            <h2>Monitoring Policy Required</h2>
            <p>An active workplace policy has not yet been published by your company admin.</p>
          </div>

          <Alert message={message} onClose={onClearMessage} />

          <div className="button-group-col" style={{ marginTop: "16px" }}>
            <button type="button" className="btn-primary full-width" onClick={onRetry}>
              Check Again
            </button>
            <button type="button" className="btn-secondary full-width" onClick={onLogout}>
              Sign Out
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (type === "declined") {
    return (
      <div className="center-wrapper">
        <div className="auth-box">
          <div className="auth-brand-header">
            <div className="error-icon-badge">×</div>
            <h2>Consent Not Provided</h2>
            <p>Monitoring consent was declined. Tracking is disabled until your company administrator reactivates your account.</p>
          </div>

          <Alert message={message} onClose={onClearMessage} />

          <button
            type="button"
            className="btn-secondary full-width"
            style={{ marginTop: "16px" }}
            onClick={onLogout}
          >
            Sign Out
          </button>
        </div>
      </div>
    );
  }

  return null;
}
