"""Log redaction for the dashboard server and launcher.

Applied to every line the server writes to its log. The dashboard handles no
prompt bodies in this increment; the patterns cover the credential shapes a
future log line could carry (API keys, bearer tokens, ``token=`` pairs) and
the server's own per-instance secrets, which are registered at startup.
"""

from __future__ import annotations

import re
import threading

REDACTED = "[redacted]"

_PATTERNS = (
    re.compile(r"(?i)(x-task-kit-token\s*[:=]\s*)\S+"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b((?:api[_-]?key|token|secret|password|passwd)\s*[=:]\s*)[^\s&;,\"']+"),
    re.compile(r"\b(sk-(?:or-)?[A-Za-z0-9_-]{16,})"),
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"\b(xox[abprs]-[A-Za-z0-9-]{10,})"),
)
# Patterns whose first group is a prefix to keep; the rest is replaced.
_KEEP_PREFIX = {0, 1, 2}

_lock = threading.Lock()
_secrets: set[str] = set()


def register_secret(value: str) -> None:
    """Redact ``value`` verbatim from every later line (the server token)."""
    if value:
        with _lock:
            _secrets.add(value)


def clear_secrets() -> None:
    with _lock:
        _secrets.clear()


def redact(text: str) -> str:
    """Return ``text`` with registered secrets and credential shapes removed."""
    with _lock:
        known = sorted(_secrets, key=len, reverse=True)
    for secret in known:
        text = text.replace(secret, REDACTED)
    for index, pattern in enumerate(_PATTERNS):
        if index in _KEEP_PREFIX:
            text = pattern.sub(lambda m: m.group(1) + REDACTED, text)
        else:
            text = pattern.sub(REDACTED, text)
    return text
