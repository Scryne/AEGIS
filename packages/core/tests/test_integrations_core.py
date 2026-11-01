"""API anahtarı biçimi, webhook imzası, yeniden deneme takvimi ve SSRF denetimi (E3.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aegis_core.security import api_keys
from aegis_core.webhooks import signing
from aegis_core.webhooks.signing import UnsafeUrlError, check_url


def test_api_key_format_and_digest() -> None:
    key, prefix, digest = api_keys.generate()
    assert key.startswith(f"aeg_{prefix}_")
    assert len(key) == 4 + 12 + 1 + 40
    assert api_keys.parse_prefix(key) == prefix
    assert api_keys.matches(key, digest)
    assert not api_keys.matches(key[:-1] + ("a" if key[-1] != "a" else "b"), digest)
    assert digest not in key  # özet anahtarın kendisi değil
    for bad in ("", "aeg_x_y", "xyz_" + key[4:], key.upper(), key + "x"):
        assert api_keys.parse_prefix(bad) is None
    assert api_keys.generate()[0] != key


def test_signature_roundtrip_tolerance_and_tamper() -> None:
    secret = signing.new_secret()
    body = b'{"type":"ping"}'
    header = signing.sign(secret, body, 1_000_000)
    assert signing.verify(secret, body, header, now=1_000_100)
    assert not signing.verify(secret, body + b" ", header, now=1_000_100)  # gövde değişti
    assert not signing.verify("whsec_baska", body, header, now=1_000_100)  # sır yanlış
    assert not signing.verify(secret, body, header, now=1_000_000 + 301)  # yeniden oynatma
    assert not signing.verify(secret, body, "bozuk", now=1_000_000)


def test_backoff_schedule_then_dead() -> None:
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    waits = [signing.next_attempt(n, t0) for n in range(1, 7)]
    assert [(w - t0).total_seconds() if w else None for w in waits] == [
        30,
        120,
        600,
        3600,
        21600,
        None,
    ]
    assert signing.next_attempt(1, t0) == t0 + timedelta(seconds=30)


def _resolver(*addrs: str):  # type: ignore[no-untyped-def]
    return lambda host, port: list(addrs)


@pytest.mark.parametrize(
    "addr",
    ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254", "::1", "0.0.0.0"],  # noqa: S104,
)
def test_private_and_metadata_targets_are_refused(addr: str) -> None:
    with pytest.raises(UnsafeUrlError, match="iç ağa"):
        check_url(
            "https://hook.example.com/x",
            allow_http=False,
            allow_private=False,
            resolver=_resolver(addr),
        )


def test_one_private_address_among_public_is_enough_to_refuse() -> None:
    with pytest.raises(UnsafeUrlError):
        check_url(
            "https://hook.example.com/x",
            allow_http=False,
            allow_private=False,
            resolver=_resolver("93.184.216.34", "10.1.1.1"),
        )


def test_scheme_credentials_and_public_ok() -> None:
    public = _resolver("93.184.216.34")
    with pytest.raises(UnsafeUrlError, match="https"):
        check_url("http://hook.example.com", allow_http=False, allow_private=False, resolver=public)
    with pytest.raises(UnsafeUrlError, match="https"):
        check_url("ftp://hook.example.com", allow_http=True, allow_private=False, resolver=public)
    with pytest.raises(UnsafeUrlError, match="parola"):
        check_url(
            "https://a:b@hook.example.com", allow_http=False, allow_private=False, resolver=public
        )
    check_url(
        "https://hook.example.com/aegis", allow_http=False, allow_private=False, resolver=public
    )
    check_url("http://localhost:9000/h", allow_http=True, allow_private=True)  # geliştirme ayarı
