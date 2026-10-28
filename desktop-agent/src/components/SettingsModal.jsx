import React, { useState } from "react";

export function SettingsModal({ isOpen, onClose, currentUrl, isLocked, onSave }) {
  const [url, setUrl] = useState(currentUrl || "");
  const [testing, setTesting] = useState(false);
  const [statusMsg, setStatusMsg] = useState(null);

  if (!isOpen) return null;

  async function handleSaveAndTest(e) {
    e.preventDefault();
    if (testing) return;
    setTesting(true);
    setStatusMsg(null);
    try {
      await onSave(url);
      setStatusMsg({ type: "success", text: "Successfully connected and saved backend URL." });
      setTimeout(() => {
        onClose();
      }, 1200);
    } catch (err) {
      setStatusMsg({ type: "error", text: err.message || "Failed to connect to backend." });
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-card">
        <div className="modal-header">
          <h3>Backend Server Settings</h3>
          <button type="button" className="modal-close-btn" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSaveAndTest}>
          <div className="form-group" style={{ marginBottom: "14px" }}>
            <label htmlFor="settings-backend-url">Backend API Endpoint</label>
            <input
              id="settings-backend-url"
              type="url"
              className="form-control"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="http://127.0.0.1:8000/api"
              disabled={isLocked || testing}
              required
            />
            <p className="field-hint">
              {isLocked
                ? "Locked by WORKPULSE_API_BASE environment variable."
                : "Default: http://127.0.0.1:8000/api (Django core backend)."}
            </p>
          </div>

          {statusMsg && (
            <div className={`alert-banner ${statusMsg.type}`} style={{ marginBottom: "14px" }}>
              <span>{statusMsg.text}</span>
            </div>
          )}

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={testing}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={isLocked || testing}>
              {testing ? "Testing..." : "Save & Connect"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

