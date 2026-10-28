import React, { useState, useEffect } from "react";

export function SessionTimer({ isRunning, startedAt }) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!isRunning || !startedAt) return;
    const interval = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => clearInterval(interval);
  }, [isRunning, startedAt]);

  if (!isRunning || !startedAt) {
    return <div className="timer-display">00:00:00</div>;
  }

  const elapsedSeconds = Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000));
  const h = String(Math.floor(elapsedSeconds / 3600)).padStart(2, "0");
  const m = String(Math.floor((elapsedSeconds % 3600) / 60)).padStart(2, "0");
  const s = String(elapsedSeconds % 60).padStart(2, "0");

  return <div className="timer-display running">{`${h}:${m}:${s}`}</div>;
}

