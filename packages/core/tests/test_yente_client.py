"""yente istemcisi testleri — istek gövdesi ve yanıt ayrıştırması (ağ yok, E1.3).

yente'nin yanıt şeması değişirse kırılacak tek yer burasıdır. Ayrıştırma bilinçli
olarak savunmacıdır: tek bir biçimsiz aday yüzünden koşunun tamamı düşerse sonuç
yanlış negatif olur.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from aegis_core.screening.yente import (
    OPENSANCTIONS_ENTITY_BASE,
    MatchQuery,
    YenteClient,
    YenteError,
    YenteUnavailableError,
    build_match_payload,
    parse_catalog,
    parse_match_response,
)


def _match_response(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"responses": {"s0": {"status": 200, "results": results}}}


# ── İstek gövdesi ────────────────────────────────────────────────────────────


def test_build_match_payload_varyantlari_tek_sorguda_toplar() -> None:
    payload = build_match_payload(
        [
            MatchQuery(
                key="s0",
                schema="Company",
                names=("yıldız inşaat", "yildiz insaat"),
                country="tr",
                identifiers={"taxNumber": "1234567890"},
            )
        ]
    )
    query = payload["queries"]["s0"]
    assert query["schema"] == "Company"
    assert query["properties"]["name"] == ["yıldız inşaat", "yildiz insaat"]
    assert query["properties"]["country"] == ["tr"]
    assert query["properties"]["taxNumber"] == ["1234567890"]


def test_build_match_payload_bos_degerleri_atar() -> None:
    payload = build_match_payload(
        [MatchQuery(key="s0", schema="Person", names=("ali", ""), identifiers={"idNumber": ""})]
    )
    query = payload["queries"]["s0"]
    assert query["properties"]["name"] == ["ali"]
    assert "idNumber" not in query["properties"]


# ── Yanıt ayrıştırması ───────────────────────────────────────────────────────


def test_parse_match_response_temel_alanlar() -> None:
    parsed = parse_match_response(
        _match_response(
            [
                {
                    "id": "NK-123",
                    "caption": "Yıldız İnşaat",
                    "schema": "Company",
                    "score": 0.91,
                    "match": True,
                    "datasets": ["default", "us_ofac_sdn"],
                    "features": {"name_literal_match": 1.0, "country_mismatch": -0.2},
                    "properties": {"topics": ["sanction"], "country": ["tr"]},
                }
            ]
        )
    )
    match = parsed["s0"][0]
    assert match.entity_id == "NK-123"
    assert match.score == pytest.approx(0.91)
    assert match.matched is True
    assert match.datasets == ("default", "us_ofac_sdn")
    assert match.topics == ("sanction",)
    assert match.features["name_literal_match"] == pytest.approx(1.0)
    assert match.is_sanctioned is True
    assert match.is_pep is False


def test_parse_match_response_skora_gore_siralar() -> None:
    parsed = parse_match_response(
        _match_response(
            [
                {"id": "a", "score": 0.5},
                {"id": "b", "score": 0.9},
                {"id": "c", "score": 0.7},
            ]
        )
    )
    assert [match.entity_id for match in parsed["s0"]] == ["b", "c", "a"]


def test_parse_match_response_bicimsiz_adayi_atar_digerlerini_korur() -> None:
    """Kimliksiz tek kayıt yüzünden diğer adaylar kaybolmamalıdır."""
    parsed = parse_match_response(
        _match_response([{"caption": "kimliksiz"}, {"id": "ok", "score": 0.8}])
    )
    assert [match.entity_id for match in parsed["s0"]] == ["ok"]


def test_parse_match_response_sorgu_hatasini_bos_liste_yapar() -> None:
    parsed = parse_match_response(
        {
            "responses": {
                "s0": {"status": 500, "error": "boom"},
                "s1": {"status": 200, "results": [{"id": "x", "score": 0.6}]},
            }
        }
    )
    assert parsed["s0"] == []
    assert [match.entity_id for match in parsed["s1"]] == ["x"]


def test_parse_match_response_eksik_alanlar_varsayilana_duser() -> None:
    match = parse_match_response(_match_response([{"id": "bare"}]))["s0"][0]
    assert match.score == 0.0
    assert match.caption == "bare"
    assert match.datasets == ()
    assert match.features == {}


def test_parse_match_response_responses_yoksa_hata() -> None:
    with pytest.raises(YenteError):
        parse_match_response({"beklenmeyen": True})


def test_pep_tespiti() -> None:
    match = parse_match_response(
        _match_response([{"id": "p", "properties": {"topics": ["role.pep"]}}])
    )["s0"][0]
    assert match.is_pep is True
    assert match.is_sanctioned is False


# ── Kaynak referansı (Invariant 4) ───────────────────────────────────────────


def test_kaynak_url_ozellikten_okunur() -> None:
    match = parse_match_response(
        _match_response(
            [{"id": "masak_dondurma-abc", "properties": {"sourceUrl": ["https://masak.example/1"]}}]
        )
    )["s0"][0]
    assert match.source_url == "https://masak.example/1"


def test_kaynak_url_yoksa_opensanctions_sayfasina_duser() -> None:
    match = parse_match_response(_match_response([{"id": "NK-9"}]))["s0"][0]
    assert match.source_url == f"{OPENSANCTIONS_ENTITY_BASE}NK-9/"


# ── Katalog / tazelik ────────────────────────────────────────────────────────


def test_parse_catalog() -> None:
    datasets = parse_catalog(
        {
            "datasets": [
                {
                    "name": "default",
                    "title": "OpenSanctions Default",
                    "version": "20260808",
                    "last_export": "2026-08-08T02:00:00Z",
                    "entity_count": 1234,
                },
                {"name": "bozuk"},
                {"eksik": "ad"},
            ]
        }
    )
    assert [dataset.name for dataset in datasets] == ["default", "bozuk"]
    assert datasets[0].last_export == datetime(2026, 8, 8, 2, 0, tzinfo=UTC)
    assert datasets[0].entity_count == 1234
    assert datasets[1].version is None


def test_ozel_veri_kumesinde_surum_damgasi_tazelige_yedek_olur() -> None:
    """MASAK gibi manifest kümelerinde ``last_export`` boştur (gerçek yente davranışı).

    Yedek olmasaydı bu kümeler her gün bayat sayılır ve alarm yorgunluğu yaratırdı.
    """
    dataset = parse_catalog(
        {"datasets": [{"name": "masak_dondurma", "version": "20260808090010"}]}
    )[0]
    assert dataset.last_export == datetime(2026, 8, 8, 9, 0, 10, tzinfo=UTC)


def test_cozulemeyen_surum_damgasi_tazelik_uretmez() -> None:
    """Sürüm sayısal bir damga değilse "bilmiyoruz" denir — uydurma tarih üretilmez."""
    dataset = parse_catalog({"datasets": [{"name": "d", "version": "v3-beta"}]})[0]
    assert dataset.last_export is None


def test_last_export_varsa_surum_damgasini_ezmez() -> None:
    dataset = parse_catalog(
        {
            "datasets": [
                {"name": "d", "version": "20200101000000", "last_export": "2026-08-08T02:00:00Z"}
            ]
        }
    )[0]
    assert dataset.last_export == datetime(2026, 8, 8, 2, 0, tzinfo=UTC)


def test_dataset_age_hours() -> None:
    dataset = parse_catalog(
        {"datasets": [{"name": "d", "last_export": "2026-08-08T02:00:00+00:00"}]}
    )[0]
    age = dataset.age_hours
    assert age is not None
    assert age > 0


# ── HTTP hata yolları (transport taklidi) ────────────────────────────────────


async def test_zaman_asimi_yente_unavailable_uretir() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("çok yavaş")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://yente") as http_client:
        client = YenteClient("http://yente", client=http_client)
        with pytest.raises(YenteUnavailableError, match="zaman aşımı"):
            await client.match(
                [MatchQuery(key="s0", schema="Company", names=("abc",))],
                cutoff=0.5,
                threshold=0.85,
            )


async def test_5xx_yente_unavailable_uretir() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(503, json={}))
    async with httpx.AsyncClient(transport=transport, base_url="http://yente") as http_client:
        client = YenteClient("http://yente", client=http_client)
        with pytest.raises(YenteUnavailableError, match="503"):
            await client.catalog()


async def test_bos_sorgu_listesi_motora_gitmez() -> None:
    """Özne yoksa HTTP çağrısı hiç yapılmamalıdır."""

    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("çağrı yapılmamalıydı")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://yente") as http_client:
        client = YenteClient("http://yente", client=http_client)
        assert await client.match([], cutoff=0.5, threshold=0.85) == {}


async def test_match_parametreleri_ve_veri_kumesi_yola_yansir() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_match_response([]))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://yente") as http_client:
        client = YenteClient("http://yente", dataset="aegis_all", client=http_client)
        await client.match(
            [MatchQuery(key="s0", schema="Company", names=("abc",))],
            cutoff=0.55,
            threshold=0.9,
            limit=7,
        )
    assert "/match/aegis_all" in seen["url"]
    assert "cutoff=0.55" in seen["url"]
    assert "threshold=0.9" in seen["url"]
    assert "limit=7" in seen["url"]
