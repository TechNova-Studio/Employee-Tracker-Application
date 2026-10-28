"""Normalize actual URL/domain telemetry; never infer a website from its title."""
import re
from urllib.parse import urlsplit, urlunsplit


def _host(value):
    try:
        host = value.rstrip('.').lower().encode('idna').decode('ascii')
    except (AttributeError, UnicodeError):
        return ''
    if len(host) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                                  for label in host.split('.')):
        return ''
    return host


def normalize_web_context(domain='', url=''):
    """An actual HTTP(S) URL takes precedence over a stale/conflicting domain.

    Strip query/fragment data before storage. A malformed/non-web URL cannot
    fall back to a supplied productive domain. Empty legacy URLs still support
    domain-only uploads, including a hostname with port/trailing dot.
    """
    raw_url = url.strip() if isinstance(url, str) else ''
    raw_domain = domain.strip() if isinstance(domain, str) else ''
    if raw_url:
        if re.search(r'[\s\x00-\x1f\\]', raw_url):
            return '', ''
        try:
            parsed = urlsplit(raw_url)
            if parsed.scheme.lower() not in ('http', 'https') or parsed.username or parsed.password:
                return '', ''
            host = _host(parsed.hostname or '')
            port = parsed.port
            if not host:
                return '', ''
            authority = host + (f':{port}' if port is not None else '')
            return host, urlunsplit((parsed.scheme.lower(), authority, parsed.path or '/', '', ''))
        except (ValueError, UnicodeError):
            return '', ''
    if not raw_domain or re.search(r'[\s\x00-\x1f\\/@?#]', raw_domain):
        return '', ''
    try:
        parsed = urlsplit('//' + raw_domain)
        parsed.port  # Reject invalid ports rather than accepting a partial hostname.
        return _host(parsed.hostname or ''), ''
    except (ValueError, UnicodeError):
        return '', ''


def url_rule_matches(pattern, url):
    """Keep textual URL patterns; constrain host/path patterns to their origin.

    The approved shared GitHub Pages CRM rule must not match an unrelated site's
    query/path merely containing the text of the Glutape CRM URL.
    """
    if not url:
        return False
    text = pattern.strip().lower()
    has_scheme = '://' in text
    candidate = text if has_scheme else 'https://' + text
    try:
        rule = urlsplit(candidate)
        host = _host(rule.hostname or '')
        if host and (has_scheme or '.' in host):
            if rule.query or rule.fragment:
                return False  # These private fields are not retained in telemetry.
            actual = urlsplit(url)
            if host != actual.hostname or (has_scheme and rule.scheme != actual.scheme):
                return False
            if rule.port is not None and rule.port != actual.port:
                return False
            rule_path = rule.path.lower() or '/'
            actual_path = actual.path.lower() or '/'
            return actual_path == rule_path.rstrip('/') or actual_path.startswith(rule_path)
    except (ValueError, UnicodeError):
        return False
    return text in url.lower()
