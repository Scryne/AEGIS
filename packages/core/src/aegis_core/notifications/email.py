"""E-posta gönderimi (SMTP). Yapılandırılmamışsa gönderim açıkça "kapalı"dır, başarılı sayılmaz.

Tek kaynak: ``Settings.smtp_*``. Sağlayıcıya özel SDK yok; her e-posta sağlayıcısı SMTP konuşur,
müşterinin kendi sunucusu da bağlanabilir. Bağlantı işçi iş parçacığında açılır, olay döngüsü
bloklanmaz.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from aegis_core.config import Settings


class EmailNotConfiguredError(Exception):
    """SMTP ayarı yok; çağıran bunu "gönderilmedi" olarak kaydeder."""


class EmailSendError(Exception):
    """Sunucu iletiyi kabul etmedi ya da bağlantı kurulamadı."""


@dataclass(frozen=True)
class OutgoingEmail:
    to: tuple[str, ...]
    subject: str
    body: str


class EmailSender(Protocol):
    @property
    def configured(self) -> bool: ...

    async def send(self, message: OutgoingEmail) -> None: ...


def build_message(message: OutgoingEmail, *, sender: str) -> EmailMessage:
    mail = EmailMessage()
    mail["From"] = sender
    # Alıcılar birbirini görmez: ekip listesi ayrı kurumlardan olmasa da gereksiz ifşa.
    mail["To"] = sender
    mail["Bcc"] = ", ".join(message.to)
    mail["Subject"] = message.subject
    mail.set_content(message.body)
    return mail


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._settings.smtp_host and self._settings.smtp_from)

    async def send(self, message: OutgoingEmail) -> None:
        if not self.configured:
            raise EmailNotConfiguredError("SMTP_HOST ve SMTP_FROM tanımlı değil.")
        await asyncio.to_thread(self._send_blocking, message)

    def _send_blocking(self, message: OutgoingEmail) -> None:
        s = self._settings
        mail = build_message(message, sender=str(s.smtp_from))
        try:
            with smtplib.SMTP(
                str(s.smtp_host), s.smtp_port, timeout=s.smtp_timeout_seconds
            ) as client:
                if s.smtp_starttls:
                    client.starttls(context=ssl.create_default_context())
                if s.smtp_username and s.smtp_password:
                    client.login(s.smtp_username, s.smtp_password)
                client.send_message(mail)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailSendError(f"SMTP gönderimi başarısız: {type(exc).__name__}") from exc


def default_sender(settings: Settings) -> EmailSender:
    return SmtpEmailSender(settings)


def recipients_text(recipients: Sequence[str]) -> str:
    return f"{len(recipients)} alıcı"
