import smtplib

from app.core.config import Settings
from app.services.email import send_email


class FakeSmtp:
    messages = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def starttls(self, context):
        self.context = context

    def login(self, username, password):
        self.credentials = (username, password)

    def send_message(self, message):
        self.messages.append(message)


class DisconnectingSmtp(FakeSmtp):
    def send_message(self, message):
        raise smtplib.SMTPServerDisconnected("connection lost after dispatch")


def test_send_email_uses_configured_smtp(monkeypatch) -> None:
    FakeSmtp.messages.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    settings = Settings(
        smtp_host="mailpit",
        smtp_port=1025,
        smtp_tls_mode="none",
        mail_from="no-reply@example.com",
        _env_file=None,
    )

    result = send_email("user@example.com", "Verify", "Text", "<b>HTML</b>", settings=settings)

    assert result.status == "sent"
    assert len(FakeSmtp.messages) == 1
    assert FakeSmtp.messages[0]["From"] == "no-reply@example.com"


def test_connection_failure_is_definitive(monkeypatch) -> None:
    def fail_connect(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP", fail_connect)
    result = send_email(
        "user@example.com",
        "Verify",
        "Text",
        settings=Settings(_env_file=None),
    )
    assert result.status == "failed"


def test_authenticated_starttls_uses_configured_credentials(monkeypatch) -> None:
    instances = []

    class RecordingSmtp(FakeSmtp):
        def __init__(self, host, port, timeout):
            super().__init__(host, port, timeout)
            instances.append(self)

    monkeypatch.setattr(smtplib, "SMTP", RecordingSmtp)
    settings = Settings(
        smtp_tls_mode="starttls",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        _env_file=None,
    )
    assert send_email("user@example.com", "Verify", "Text", settings=settings).status == "sent"
    assert instances[0].credentials == ("smtp-user", "smtp-password")
    assert instances[0].context is not None


def test_disconnect_after_connection_is_unknown(monkeypatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", DisconnectingSmtp)
    result = send_email(
        "user@example.com",
        "Verify",
        "Text",
        settings=Settings(_env_file=None),
    )
    assert result.status == "unknown"
