"""Email channel. Empty SMTP_HOST selects the console channel, which logs
the message and keeps the last one in memory so dev pages can show the link."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger("safecircles.email")
settings = get_settings()

_last_message: dict[str, str] = {}


def send(to: str, subject: str, body: str) -> None:
    _last_message.update({"to": to, "subject": subject, "body": body})
    if not settings.smtp_host:
        log.info("EMAIL to=%s subject=%r\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"] = f"{settings.email_from_name} <{settings.email_from}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        s.starttls()
        s.send_message(msg)


def last_message() -> dict[str, str]:
    return dict(_last_message)
