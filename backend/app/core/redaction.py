from __future__ import annotations

import re

from app.core.config import get_settings

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"websocket[_-]?token|authorization)(\s*[:=]\s*)([^\s,;\"'}]+|\"[^\"]*\"|'[^']*')"
)


def redact_sensitive_text(value: str) -> str:
    """Remove known secrets and common credential assignments from persisted logs."""

    redacted = value
    settings = get_settings()
    known_secrets = (settings.app_secret_key, settings.openai_api_key)
    for secret in known_secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return _SENSITIVE_ASSIGNMENT.sub(r"\1\2[REDACTED]", redacted)
