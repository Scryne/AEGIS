"""Webhook imzası, yeniden deneme takvimi ve hedef adres güvenliği (E3.4) — saf çekirdek.

**İmza.** Her teslim ``X-Aegis-Signature: t=<unix>,v1=<hex>`` başlığı taşır;
``v1 = HMAC-SHA256(secret, f"{t}.{gövde}")``. Alıcı zamanı (±5 dk) ve imzayı sabit zamanlı
karşılaştırmayla doğrular; aynı gövde başka zamanda yeniden oynatılamaz.

**Yeniden deneme.** 2xx dışı ya da ağ hatası: 30 sn, 2 dk, 10 dk, 1 sa, 6 sa sonra; altıncı
başarısızlıkta teslim ``dead`` olur ve elle yeniden gönderilebilir.

**Hedef adres (SSRF).** Webhook adresi müşterinin yazdığı bir URL'dir ve istek bizim ağımızdan
çıkar. Bu yüzden: yalnız ``https`` (geliştirme ayarıyla ``http``), kullanıcı adı/parola içermez,
ad çözümlemesinin döndürdüğü **her** adres herkese açık olmalıdır (loopback, özel ağ, bağlantı
yerel, ayrılmış, çok noktaya yayın reddedilir). Kontrol kayıtta ve her teslimde yapılır (DNS
sonradan değişebilir).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import socket
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from urllib.parse import urlsplit

SIGNATURE_HEADER = "X-Aegis-Signature"
EVENT_HEADER = "X-Aegis-Event"
DELIVERY_HEADER = "X-Aegis-Delivery"
TOLERANCE_SECONDS = 300

BACKOFF_SECONDS: tuple[int, ...] = (30, 120, 600, 3600, 21600)
MAX_ATTEMPTS = len(BACKOFF_SECONDS) + 1

EVENTS: tuple[str, ...] = ("screening.completed", "alert.raised", "case.updated", "batch.completed")


def new_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def sign(secret: str, body: bytes, timestamp: int) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


def verify(secret: str, body: bytes, header: str, now: int) -> bool:
    """Alıcı tarafı doğrulama (belgedeki örnek kodun Python karşılığı; testlerde kullanılır)."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(now - ts) > TOLERANCE_SECONDS:
        return False
    expected = sign(secret, body, ts).split("v1=", 1)[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))


def next_attempt(attempts: int, now: datetime) -> datetime | None:
    """``attempts`` başarısız denemeden sonra bir sonraki zaman; hak bittiyse ``None``."""
    if attempts >= MAX_ATTEMPTS:
        return None
    return now + timedelta(seconds=BACKOFF_SECONDS[min(attempts, len(BACKOFF_SECONDS)) - 1])


class UnsafeUrlError(ValueError):
    pass


Resolver = Callable[[str, int], Iterable[str]]


def _system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def check_url(
    url: str, *, allow_http: bool, allow_private: bool, resolver: Resolver | None = None
) -> None:
    """URL güvenli değilse ``UnsafeUrlError``; mesaj kullanıcıya gösterilebilir."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("https", "http") or (parts.scheme == "http" and not allow_http):
        raise UnsafeUrlError("Webhook adresi https ile başlamalı.")
    if not parts.hostname:
        raise UnsafeUrlError("Webhook adresinde sunucu adı yok.")
    if parts.username or parts.password:
        raise UnsafeUrlError("Webhook adresi kullanıcı adı/parola içeremez; imza kullanılır.")
    if len(url) > 500:
        raise UnsafeUrlError("Webhook adresi 500 karakteri aşamaz.")
    if allow_private:
        return
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = list((resolver or _system_resolver)(parts.hostname, port))
    except OSError as exc:
        raise UnsafeUrlError("Webhook sunucu adı çözümlenemedi.") from exc
    if not addresses:
        raise UnsafeUrlError("Webhook sunucu adı çözümlenemedi.")
    for raw in addresses:
        ip = ipaddress.ip_address(raw.split("%", 1)[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
            or not ip.is_global
        ):
            raise UnsafeUrlError("Webhook adresi iç ağa ya da ayrılmış bir adrese çıkamaz.")
