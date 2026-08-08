"""GLEIF istemcisi — yanıt ayrıştırma ve dışarı ne gittiği (E1.4).

İki şeyi sabitler:

1. **Ayrıştırma savunmacıdır**: GLEIF alan adları değişirse eksik zenginleştirme olur,
   çökme değil.
2. **Dışarı yalnız LEI çıkar** (KVKK, Invariant 3): istek URL'inde ad/adres/vergi no
   bulunmamalıdır.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from aegis_core.entities.gleif import (
    GleifClient,
    GleifError,
    GleifNotFoundError,
    parse_lei_record,
)

GECERLI_LEI = "529900T8BM49AURSDO55"

ORNEK_YANIT: dict[str, Any] = {
    "data": {
        "id": GECERLI_LEI,
        "attributes": {
            "entity": {
                "legalName": {"name": "YILDIZ INSAAT SANAYI VE TICARET LIMITED SIRKETI"},
                "legalAddress": {
                    "addressLines": ["Cumhuriyet Mah. No:15"],
                    "city": "Istanbul",
                    "postalCode": "34360",
                    "country": "TR",
                },
                "registeredAs": "0123456789012345",
                "legalForm": {"id": "AXSB"},
                "status": "ACTIVE",
            },
            "registration": {"status": "ISSUED"},
        },
    }
}


def test_yanit_ayristirma() -> None:
    record = parse_lei_record(ORNEK_YANIT)
    assert record.lei == GECERLI_LEI
    assert record.legal_name == "YILDIZ INSAAT SANAYI VE TICARET LIMITED SIRKETI"
    assert record.country == "TR"
    assert record.address is not None
    assert "Cumhuriyet" in record.address
    assert "Istanbul" in record.address
    assert record.status == "ACTIVE"
    assert record.registration_authority_id == "0123456789012345"
    assert GECERLI_LEI in record.source_url


def test_liste_biciminde_yanit_da_okunur() -> None:
    record = parse_lei_record({"data": [ORNEK_YANIT["data"]]})
    assert record.lei == GECERLI_LEI


def test_eksik_alanlar_none_uretir_cokmez() -> None:
    """Alan adları değişirse zenginleştirme boş döner, akış düşmez."""
    record = parse_lei_record({"data": {"id": GECERLI_LEI, "attributes": {}}})
    assert record.legal_name is None
    assert record.address is None
    assert record.country is None


def test_bos_yanit_not_found() -> None:
    with pytest.raises(GleifNotFoundError):
        parse_lei_record({"data": []})


async def test_yalniz_lei_kodu_disari_cikar() -> None:
    """KVKK kapısı: istekte ad, adres ya da vergi numarası bulunmamalı."""
    gorulen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        gorulen["url"] = str(request.url)
        gorulen["content"] = request.content.decode("utf-8")
        return httpx.Response(200, json=ORNEK_YANIT)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://gleif.test") as http:
        client = GleifClient("https://gleif.test", client=http)
        await client.fetch(GECERLI_LEI)

    assert GECERLI_LEI in gorulen["url"]
    assert gorulen["content"] == ""  # GET, gövde yok
    for yasakli in ("Yıldız", "Cumhuriyet", "4840847211", "10000000146"):
        assert yasakli not in gorulen["url"]


async def test_gecersiz_lei_dis_cagri_yapmaz() -> None:
    """Biçimsiz kod için dış servise gidilmez (gereksiz çağrı + izde gürültü)."""

    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("çağrı yapılmamalıydı")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://gleif.test") as http:
        client = GleifClient("https://gleif.test", client=http)
        with pytest.raises(GleifError):
            await client.fetch("GECERSIZ")


async def test_404_not_found_uretir() -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(404, json={}))
    async with httpx.AsyncClient(transport=transport, base_url="https://gleif.test") as http:
        client = GleifClient("https://gleif.test", client=http)
        with pytest.raises(GleifNotFoundError):
            await client.fetch(GECERLI_LEI)


async def test_zaman_asimi_gleif_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("yavaş")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://gleif.test") as http:
        client = GleifClient("https://gleif.test", client=http)
        with pytest.raises(GleifError, match="zaman aşımı"):
            await client.fetch(GECERLI_LEI)
