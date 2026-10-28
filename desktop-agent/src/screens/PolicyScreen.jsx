import React from "react";
import { Alert } from "../components/Alert";

export function PolicyScreen({
  policy,
  message,
  onClearMessage,
  onAccept,
  onDecline,
  onReturnDashboard,
  onLogout,
}) {
  const isAccepted = Boolean(policy?.accepted);

  return (
    <div className="center-wrapper">
      <div className="policy-box">
        <div className="policy-header-row">
          <div>
            <h2>{policy?.policy?.title || "Workplace Monitoring Policy"}</h2>
            <p className="policy-subtext">
              Review and acknowledge the active organization policy.
            </p>
          </div>
          {isAccepted && (
            <span className="badge-accepted">Consent Acknowledged</span>
          )}
        </div>

        <Alert message={message} onClose={onClearMessage} />

        <div className="policy-document-body">
          {policy?.policy?.body || "No policy content available."}
        </div>

        <div className="policy-footer-actions">
          <button type="button" className="btn-secondary" onClick={onLogout}>
            Sign Out
          </button>

          <button
            type="button"
            className="btn-danger-outline"
            onClick={onDecline}
          >
            {isAccepted ? "Withdraw Consent" : "Decline"}
          </button>

          {isAccepted ? (
            <button
              type="button"
              className="btn-primary"
              onClick={onReturnDashboard}
            >
              Back to Work Session
            </button>
          ) : (
            <button
              type="button"
              className="btn-primary"
              onClick={onAccept}
            >
              Accept & Continue
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

