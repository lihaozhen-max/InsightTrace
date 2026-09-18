from app.core.config import get_settings
from app.core.redaction import redact_sensitive_text


def test_redacts_known_secrets_and_credential_assignments() -> None:
    settings = get_settings()
    value = (
        f"app_secret={settings.app_secret_key} "
        "password=hunter2 access_token: abc123 ordinary=value"
    )

    redacted = redact_sensitive_text(value)

    assert settings.app_secret_key not in redacted
    assert "hunter2" not in redacted
    assert "abc123" not in redacted
    assert "ordinary=value" in redacted
    assert redacted.count("[REDACTED]") == 3
