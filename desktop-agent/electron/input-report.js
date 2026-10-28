// Support metadata only. Never serialize an API request, authorization header,
// raw native event, application/window title, or the authenticated employee.
function inputReport({ event, version, platform, arch, running, capture, attempt = null, at = Date.now() }) {
  const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
  return {
    at: new Date(at).toISOString(),
    event,
    app_version: version,
    platform,
    arch,
    session_running: Boolean(running),
    capture: {
      state: capture.state,
      active: Boolean(capture.active),
      error_code: capture.error_code || "",
      error_detail: capture.error_detail || "",
      session_keyboard_count: count(capture.session_keyboard_count),
      session_mouse_count: count(capture.session_mouse_count),
      last_input_at: capture.last_input_at ?? null,
    },
    last_activity_attempt: attempt ? {
      at: attempt.at,
      outcome: attempt.outcome,
      http_status: Number.isInteger(attempt.http_status) ? attempt.http_status : null,
      keyboard_count: count(attempt.keyboard_count),
      mouse_count: count(attempt.mouse_count),
      server_keyboard_count: count(attempt.server_keyboard_count),
      server_mouse_count: count(attempt.server_mouse_count),
    } : null,
  };
}

module.exports = { inputReport };
