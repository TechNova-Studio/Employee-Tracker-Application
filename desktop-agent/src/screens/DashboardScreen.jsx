import React, { useMemo } from "react";
import { SessionTimer } from "../components/SessionTimer";
import { Alert } from "../components/Alert";

export function DashboardScreen({
  status,
  lastSession,
  cfg,
  message,
  onClearMessage,
  onStartSession,
  onStopSession,
  onReviewPolicy,
}) {
  const isRunning = Boolean(status?.runningSession);
  const activeSession = status?.runningSession;

  // Determine current or last session for timestamps
  const startedAt = activeSession?.started_at || lastSession?.started_at;
  const stoppedAt = isRunning ? null : (lastSession?.stopped_at || activeSession?.stopped_at);

  const formatTime = (ts) => {
    if (!ts) return "—";
    try {
      return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "—";
    }
  };

  const formattedStartTime = useMemo(() => formatTime(startedAt), [startedAt]);
  const formattedStopTime = useMemo(() => {
    if (isRunning) return "In Progress";
    return formatTime(stoppedAt);
  }, [isRunning, stoppedAt]);

  const shiftDurationText = useMemo(() => {
    if (isRunning) return "In Progress";
    if (startedAt && stoppedAt) {
      const diffSec = Math.max(0, Math.floor((new Date(stoppedAt) - new Date(startedAt)) / 1000));
      const hrs = Math.floor(diffSec / 3600);
      const mins = Math.floor((diffSec % 3600) / 60);
      return `${hrs}h ${mins}m`;
    }
    return "0h 0m";
  }, [isRunning, startedAt, stoppedAt]);

  const activeWorkText = useMemo(() => {
    if (isRunning) return "Live (Tracking)";
    if (lastSession?.active_seconds != null) {
      const actSec = Number(lastSession.active_seconds) || 0;
      const hrs = Math.floor(actSec / 3600);
      const mins = Math.floor((actSec % 3600) / 60);
      return `${hrs}h ${mins}m`;
    }
    if (startedAt && stoppedAt) {
      const diffSec = Math.max(0, Math.floor((new Date(stoppedAt) - new Date(startedAt)) / 1000));
      const hrs = Math.floor(diffSec / 3600);
      const mins = Math.floor((diffSec % 3600) / 60);
      return `${hrs}h ${mins}m`;
    }
    return "0h 0m";
  }, [isRunning, lastSession, startedAt, stoppedAt]);

  const lastDurationText = shiftDurationText;

  const todayStr = useMemo(() => {
    return new Date().toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  }, []);

  return (
    <div className="dashboard-container">
      <Alert message={message} onClose={onClearMessage} />

      {/* Main Work Session Tracker */}
      <section className="tracker-panel">
        <div className="tracker-status-row">
          <span className={`status-tag ${isRunning ? "active" : "inactive"}`}>
            <span className={`status-bullet ${isRunning ? "active" : "inactive"}`} />
            {isRunning ? "Shift Active" : "Shift Stopped"}
          </span>
          <span className="tracker-date-hint">{todayStr}</span>
        </div>

        <SessionTimer isRunning={isRunning} startedAt={activeSession?.started_at} />

        <div className="tracker-meta-text">
          {isRunning ? (
            <span>Check-in registered at <strong>{formattedStartTime}</strong>. Shift hours are being recorded for attendance.</span>
          ) : stoppedAt ? (
            <span>Last check-out registered at <strong>{formattedStopTime}</strong> ({lastDurationText}).</span>
          ) : (
            <span>Ready to work. Click below to punch in and record your attendance for today.</span>
          )}
        </div>

        <div className="tracker-button-container">
          {isRunning ? (
            <button
              type="button"
              className="btn-stop"
              onClick={onStopSession}
            >
              Punch Out
            </button>
          ) : (
            <button
              type="button"
              className="btn-start"
              onClick={onStartSession}
            >
              Punch In
            </button>
          )}
        </div>
      </section>

      {/* Zoho-Style Attendance & Information Grid */}
      <div className="cards-grid">
        {/* Zoho-Style Attendance Punch Card */}
        <div className="content-card">
          <div className="card-heading">Shift Attendance</div>

          {/* Zoho-Style Two-Column Punch Box */}
          <div className="punch-box-container">
            <div className="punch-item check-in">
              <div className="punch-item-header">
                <span className="punch-dot check-in" />
                <span className="punch-title">CHECK-IN</span>
              </div>
              <div className="punch-time">{formattedStartTime}</div>
              <div className="punch-subtitle">Shift Start</div>
            </div>

            <div className={`punch-item check-out ${isRunning ? "in-progress" : ""}`}>
              <div className="punch-item-header">
                <span className={`punch-dot check-out ${isRunning ? "active" : ""}`} />
                <span className="punch-title">CHECK-OUT</span>
              </div>
              <div className="punch-time">{formattedStopTime}</div>
              <div className="punch-subtitle">{isRunning ? "Live Shift" : "Shift Stopped"}</div>
            </div>
          </div>

          <div className="card-data-list" style={{ marginTop: "6px" }}>
            <div className="data-row">
              <span className="data-label">Shift Duration</span>
              <span className="data-value">{shiftDurationText}</span>
            </div>
            <div className="data-row">
              <span className="data-label">Active Work</span>
              <span className="data-value text-success">{activeWorkText}</span>
            </div>
            <div className="data-row">
              <span className="data-label">Workstation</span>
              <span className="data-value">{cfg?.PLATFORM || "Windows"}</span>
            </div>
          </div>
        </div>

        {/* Attendance Overview & Shift Summary */}
        <div className="content-card">
          <div className="card-heading-row">
            <div className="card-heading" style={{ marginBottom: 0 }}>Attendance Overview</div>
            <span className={`attendance-badge ${isRunning ? "present" : lastSession ? "completed" : "pending"}`}>
              {isRunning ? "● Present" : lastSession ? "● Completed" : "○ Not Checked In"}
            </span>
          </div>

          <p className="card-description" style={{ marginTop: "4px" }}>
            Daily attendance and work hours are automatically synchronized with your organization's HR portal.
          </p>

          <div className="attendance-metrics-grid">
            <div className="attendance-metric-item">
              <span className="metric-label">Shift Type</span>
              <span className="metric-val">Regular Shift (9h)</span>
            </div>
            <div className="attendance-metric-item">
              <span className="metric-label">Daily Target</span>
              <span className="metric-val">9h 00m</span>
            </div>
          </div>

          <div className="attendance-guidelines-box">
            <div className="guidelines-title">Attendance Notes</div>
            <ul className="attendance-list">
              <li>Punch in upon starting work to log your daily attendance.</li>
              <li>Punch out when finishing shift.</li>
              <li>Hours logged automatically reflect on your monthly timesheet.</li>
            </ul>
          </div>

          {onReviewPolicy && (
            <div className="card-action-bar">
              <button
                type="button"
                className="btn-text-link"
                onClick={onReviewPolicy}
              >
                View Attendance Guidelines →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
