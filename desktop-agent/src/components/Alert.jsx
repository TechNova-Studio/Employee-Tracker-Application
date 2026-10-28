import React from "react";

export function Alert({ message, onClose }) {
  if (!message) return null;
  const type = message.type || "info";

  return (
    <div className={`alert-banner ${type}`} role="alert">
      <span>{message.text}</span>
      {onClose && (
        <button
          type="button"
          className="alert-close-btn"
          onClick={onClose}
          aria-label="Dismiss message"
        >
          ×
        </button>
      )}
    </div>
  );
}

