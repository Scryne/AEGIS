"""Uçtan uca tarama RECALL TABANI — gerçek yente + Elasticsearch (E1.3).

``test_normalization_recall.py`` normalizasyonun kendi içinde tutarlı olduğunu ölçer;
bu dosya asıl soruyu sorar: **varyantla arayan kullanıcı, listedeki kaydı bulabiliyor mu?**
Zincirin tamamı koşar — normalizasyon → ad varyantları → yente sorgusu → skor.

Veri kümesi bilinçli olarak küçüktür (``evals/fixtures/entities.ftm.json``): yalnız
referans yazımlar indekslenir. Varyantlar indekse **eklenmez**; eklenseydi test kendi
kendini doğrulayan bir tautoloji olurdu.

Koşturma::

    docker compose -f infra/compose/docker-compose.evals.yml up -d
    YENTE_TEST_URL=http://localhost:8002 uv run pytest -m screening

``YENTE_TEST_URL`` verilmezse testler atlanır (yerel geliştirmede 4 GB'lık ES ayağa
kaldırmak zorunlu olmasın diye). CI'da ayrı bir iş bunu koşar.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from aegis_core.screening.normalization import SubjectType, name_variants, normalize_name
from aegis_core.screening.thresholds import DEFAULT_THRESHOLDS
from aegis_core.screening.yente import MatchQuery, YenteClient

pytestmark = pytest.mark.screening

CASES_PATH = Path(__file__).parent / "turkish_screening" / "cases.json"
EVAL_DATASET = "aegis_eval"

# Kapı: her varyant, kendi kaydını **otomatik eleme eşiğinin üstünde** bulmalıdır.
# "Sonuçlarda bir yerde var" yetmez — eşiğin altında kalan aday sahada otomatik elenir,
# yani kullanıcı açısından kaçmış demektir.
RECALL_FLOOR = 1.0
MIN_SCORE = DEFAULT_THRESHOLDS.auto_dismiss_below


def _cases() -> list[dict[str, Any]]:
    with CASES_PATH.open(encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data["cases"]


CASES = _cases()


@pytest.fixture(scope="session")
def yente_url() -> str:
    url = os.environ.get("YENTE_TEST_URL")
    if not url:
        pytest.skip("YENTE_TEST_URL ayarlanmadı (docker compose -f ...evals.yml up -d)")
    return url


@pytest.fixture(scope="session")
def yente_ready(yente_url: str) -> None:
    """yente ayakta ve değerlendirme veri kümesi indekslenmiş mi."""
    try:
        response = httpx.get(f"{yente_url}/catalog", timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:  # pragma: no cover - ortam hatası
        pytest.fail(f"yente'ye ulaşılamadı ({yente_url}): {exc}")
    names = {dataset.get("name") for dataset in response.json().get("datasets", [])}
    assert EVAL_DATASET in names, (
        f"'{EVAL_DATASET}' veri kümesi indekste yok (katalog: {sorted(names)}). "
        "yente indekslemeyi bitirdi mi?"
    )


async def _search(url: str, name: str, subject_type: SubjectType) -> list[tuple[str, float]]:
    """Bir adı ürünün kullandığı yolla arar; (varlık kimliği, skor) çiftleri döndürür."""
    normalized = normalize_name(name, subject_type)
    async with YenteClient(url, dataset=EVAL_DATASET, timeout_seconds=30.0) as client:
        results = await client.match(
            [
                MatchQuery(
                    key="s0",
                    schema="Person" if subject_type is SubjectType.PERSON else "Company",
                    names=name_variants(normalized),
                    country="tr",
                )
            ],
            cutoff=DEFAULT_THRESHOLDS.candidate_cutoff,
            threshold=DEFAULT_THRESHOLDS.auto_flag_at,
            limit=10,
        )
    return [(match.entity_id, match.score) for match in results.get("s0", [])]


@pytest.mark.usefixtures("yente_ready")
@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_varyantlar_kaydi_bulur(case: dict[str, Any], yente_url: str) -> None:
    """Vaka bazında uçtan uca recall."""
    subject_type = SubjectType(case["subject_type"])
    expected_id = f"aegis-eval-{case['id']}"
    kacan: list[str] = []
    for variant in case["variants"]:
        results = dict(await _search(yente_url, variant, subject_type))
        score = results.get(expected_id)
        if score is None or score < MIN_SCORE:
            kacan.append(f"{variant!r} → skor {score}")
    assert not kacan, f"[{case['id']}] eşiğin üstünde bulunamayan varyantlar:\n  " + "\n  ".join(
        kacan
    )


@pytest.mark.usefixtures("yente_ready")
async def test_referans_yazim_kendini_bulur(yente_url: str) -> None:
    """Sağlık kontrolü: referans yazımın kendisi bulunamıyorsa indeks bozuktur."""
    for case in CASES:
        results = dict(
            await _search(yente_url, case["canonical"], SubjectType(case["subject_type"]))
        )
        assert f"aegis-eval-{case['id']}" in results, f"{case['id']}: referans yazım bulunamadı"


@pytest.mark.usefixtures("yente_ready")
async def test_alakasiz_ad_eslesme_uretmez(yente_url: str) -> None:
    """Kesinlik emniyeti: tamamen alakasız bir ad, eşiğin üstünde aday getirmemeli."""
    results = await _search(yente_url, "Zebra Kuantum Mühendislik", SubjectType.COMPANY)
    yuksek = [(entity_id, score) for entity_id, score in results if score >= MIN_SCORE]
    assert not yuksek, f"Alakasız ad eşleşme üretti: {yuksek}"
