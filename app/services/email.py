import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Literal

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class EmailSendResult:
    status: Literal["sent", "failed", "unknown"]
    error: str | None = None


def send_email(
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    *,
    settings: Settings | None = None,
) -> EmailSendResult:
    config = settings or get_settings()
    message = EmailMessage()
    message["From"] = config.mail_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    connected = False
    client: smtplib.SMTP
    try:
        if config.smtp_tls_mode == "tls":
            client = smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_port,
                timeout=10,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10)
        connected = True
        with client:
            if config.smtp_tls_mode == "starttls":
                client.starttls(context=ssl.create_default_context())
            if config.smtp_username:
                client.login(config.smtp_username, config.smtp_password or "")
            client.send_message(message)
        return EmailSendResult(status="sent")
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
        return EmailSendResult(status="failed", error=type(exc).__name__)
    except (TimeoutError, smtplib.SMTPServerDisconnected) as exc:
        status: Literal["failed", "unknown"] = "unknown" if connected else "failed"
        return EmailSendResult(status=status, error=type(exc).__name__)
    except (OSError, smtplib.SMTPException) as exc:
        return EmailSendResult(status="failed", error=type(exc).__name__)

