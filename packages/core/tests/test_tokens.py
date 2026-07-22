"""JWT token birim testleri: tür zorlaması, süre, imza."""

from __future__ import annotations

import uuid

import jwt
import pytest

from aegis_core.security.tokens import (
    TYPE_ACCESS,
    TYPE_REFRESH,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_reset_token,
    decode_token,
)

SECRET = "unit-test-secret-0123456789-abcdef"


def test_access_token_roundtrip() -> None:
    uid, tid = uuid.uuid4(), uuid.uuid4()
    token = create_access_token(
        user_id=uid, tenant_id=tid, role="owner", secret=SECRET, expires_in_minutes=60
    )
    payload = decode_token(token, SECRET, expected_type=TYPE_ACCESS)
    assert payload.sub == str(uid)
    assert payload.tenant_id == str(tid)
    assert payload.role == "owner"
    assert payload.typ == TYPE_ACCESS


def test_refresh_token_cannot_be_used_as_access() -> None:
    token = create_refresh_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="analyst",
        secret=SECRET,
        expires_in_days=30,
    )
    # refresh olarak çözülür
    assert decode_token(token, SECRET, expected_type=TYPE_REFRESH).typ == TYPE_REFRESH
    # ama access beklenirken reddedilir
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, SECRET, expected_type=TYPE_ACCESS)


def test_wrong_secret_rejected() -> None:
    token = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="owner",
        secret=SECRET,
        expires_in_minutes=60,
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(token, "baska-secret", expected_type=TYPE_ACCESS)


def test_expired_token_rejected() -> None:
    token = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role="owner",
        secret=SECRET,
        expires_in_minutes=-1,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, SECRET, expected_type=TYPE_ACCESS)


def test_reset_token_is_single_purpose() -> None:
    uid = uuid.uuid4()
    reset = create_password_reset_token(user_id=uid, secret=SECRET, expires_in_minutes=30)
    assert decode_reset_token(reset, SECRET).sub == str(uid)
    # reset token bir access token olarak çözülemez (şema/tür uymaz)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(reset, SECRET, expected_type=TYPE_ACCESS)
