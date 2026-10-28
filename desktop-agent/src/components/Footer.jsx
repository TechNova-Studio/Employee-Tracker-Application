import React from "react";

export function Footer({ queueLength = 0, appVersion = "1.0.0", onSync, syncing }) {
  return (
    <footer className="app-footer">
      <div className="footer-left">
        {queueLength > 0 ? (
          <div className="sync-status warning">
            <span className="dot warning" />
            <span>{queueLength} record{queueLength === 1 ? "" : "s"} offline</span>
            {onSync && (
              <button
                type="button"
                className="btn-sync-link"
                onClick={onSync}
                disabled={syncing}
              >
                {syncing ? "Syncing..." : "Sync Now"}
              </button>
            )}
          </div>
        ) : (
          <div className="sync-status ok">
            <span className="dot ok" />
            <span>All activity synchronized</span>
          </div>
        )}
      </div>

      <div className="footer-right">
        <span>BOLD WorkPulse v{appVersion}</span>
      </div>
    </footer>
  );
}

