import React, { useState, useRef, useEffect } from "react";
import { Alert } from "../components/Alert";
import { CrmLoginButton } from "../components/CrmLoginButton";

export function LoginScreen({ onLogin, onCrmLogin, busy, message, onClearMessage, apiBase }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const emailInputRef = useRef(null);

  useEffect(() => {
    // Automatically focus the input when the screen mounts or busy toggles off
    const timer = setTimeout(() => {
      if (emailInputRef.current) {
        emailInputRef.current.focus();
      }
    }, 60);
    return () => clearTimeout(timer);
  }, [busy]);

  function handleSubmit(e) {
    e.preventDefault();
    if (!email.trim() || !password) return;
    onLogin({ email: email.trim(), password });
  }

  return (
    <div className="center-wrapper">
      <div className="auth-box">
        <div className="auth-brand-header">
          <div className="auth-logo">WP</div>
          <h2>Employee Sign In</h2>
          <p>BOLD WorkPulse Desktop Agent</p>
        </div>

        <Alert message={message} onClose={onClearMessage} />

        {onCrmLogin && (
          <CrmLoginButton
            onCrmLogin={onCrmLogin}
            busy={busy}
            apiBase={apiBase}
          />
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="login-email">Work Email or Username</label>
            <input
              ref={emailInputRef}
              id="login-email"
              type="text"
              className="form-control"
              placeholder="e.g. employee@company.com"
              autoComplete="username"
              autoFocus
              required
              disabled={busy}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="login-password">Password</label>
            <div className="password-input-group">
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                className="form-control"
                placeholder="Enter password"
                autoComplete="current-password"
                required
                disabled={busy}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          <button type="submit" className="btn-primary full-width" disabled={busy}>
            {busy ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
