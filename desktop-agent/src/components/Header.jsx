import React from "react";

export function Header({ currentUser, currentCompany, onLogout }) {
  const userEmail = currentUser?.email || "";
  const companyName = currentCompany?.name || "";
  const initials = userEmail ? userEmail.slice(0, 2).toUpperCase() : "";

  return (
    <header className="app-header">
      <div className="brand-section">
        <div className="brand-badge">WP</div>
        <div className="brand-text">
          <span className="brand-title">BOLD WorkPulse</span>
          <span className="brand-subtitle">Desktop Agent</span>
        </div>
      </div>

      <div className="header-actions">
        {currentUser && (
          <>
            <div className="user-profile-badge">
              <span className="user-initials">{initials}</span>
              <div className="user-info-text">
                <span className="user-email">{userEmail}</span>
                {companyName && <span className="user-company">{companyName}</span>}
              </div>
            </div>

            <button type="button" className="btn-logout" onClick={onLogout}>
              Sign Out
            </button>
          </>
        )}
      </div>
    </header>
  );
}
