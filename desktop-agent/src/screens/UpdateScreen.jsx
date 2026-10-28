import React from "react";
import { Alert } from "../components/Alert";

export function UpdateScreen({ version, currentVersion, message, onClearMessage, onDownload, onLogout }) {
  return (
    <div className="center-wrapper">
      <div className="auth-box">
        <div className="auth-brand-header">
          <div className="warning-icon-badge">!</div>
          <h2>Update Required</h2>
          <p>Installed version is below the minimum required version.</p>
        </div>

        <Alert message={message} onClose={onClearMessage} />

        <div className="version-info-box">
          <div className="data-row">
            <span className="data-label">Installed Version:</span>
            <span className="data-value">{currentVersion || "1.0.0"}</span>
          </div>
          <div className="data-row">
            <span className="data-label">Required Minimum:</span>
            <span className="data-value">{version?.minimum_supported_version || "—"}</span>
          </div>
        </div>

        {version?.release_notes && (
          <div className="release-notes-box">
            <strong>Release Notes:</strong>
            <p>{version.release_notes}</p>
          </div>
        )}

        {version?.download_url ? (
          <button
            type="button"
            className="btn-primary full-width"
            onClick={() => onDownload(version.download_url)}
          >
            Download Latest Update
          </button>
        ) : (
          <p className="field-hint" style={{ textAlign: "center", margin: "16px 0" }}>
            Please contact your organization administrator for an updated installer.
          </p>
        )}

        <button
          type="button"
          className="btn-secondary full-width"
          style={{ marginTop: "10px" }}
          onClick={onLogout}
        >
          Sign Out
        </button>
      </div>
    </div>
  );
}

