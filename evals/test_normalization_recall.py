"""Türkçe normalizasyon RECALL TABANI — CI kapısı (E1.3).

CLAUDE.md: *"Bir **recall floor (~%100)** CI'da 'tarama tamam' demenin ön koşuludur;
yanlış negatifler tehlikeli hatadır."* Bu dosya o kapının Docker gerektirmeyen,
her push'ta koşan katmanıdır.

**Ölçüt.** ``evals/turkish_screening/cases.json`` içindeki her vakada, aynı gerçek
varlığın bütün yazımları referans yazımla **aynı** kanonik anahtara inmelidir. Tek bir
varyantın kayması, sahada kaçan bir yaptırım eşleşmesi demektir; bu yüzden taban
%100'dür ve tolerans yoktur.

İkinci katman — gerçek yente/Elasticsearch üzerinden uçtan uca recall — ayrı bir
işarette (``-m screening``) ``test_screening_recall.py`` içindedir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aegis_core.screening.normalization import SubjectType, normalize_name

CASES_PATH = Path(__file__).parent / "turkish_screening" / "cases.json"

# Recall tabanı: gevşetilmesi bilinçli bir karar olmalıdır (bkz. modül başlığı).
RECALL_FLOOR = 1.0
# Setin anlamlı kalması için asgari büyüklük (Phase 0 hedefi: 30–50 vaka).
MIN_CASES = 30


def _load() -> dict[str, Any]:
    with CASES_PATH.open(encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


DATASET = _load()
CASES: list[dict[str, Any]] = DATASET["cases"]


def test_veri_seti_yeterince_buyuk() -> None:
    assert len(CASES) >= MIN_CASES, f"Değerlendirme seti küçüldü: {len(CASES)} < {MIN_CASES}"
    assert sum(len(case["variants"]) for case in CASES) >= 90


def test_vaka_kimlikleri_tekil() -> None:
    identifiers = [case["id"] for case in CASES]
    assert len(identifiers) == len(set(identifiers))


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_varyantlar_referansla_ayni_anahtara_iner(case: dict[str, Any]) -> None:
    """Vaka bazında recall: her varyant referansla aynı kanonik anahtara inmeli."""
    subject_type = SubjectType(case["subject_type"])
    expected = normalize_name(case["canonical"], subject_type).sort_key
    hatalar = []
    for variant in case["variants"]:
        actual = normalize_name(variant, subject_type).sort_key
        if actual != expected:
            hatalar.append(f"{variant!r} → {actual!r} (beklenen {expected!r})")
    assert not hatalar, "Kaçan varyantlar:\n  " + "\n  ".join(hatalar)


def test_toplam_recall_tabani() -> None:
    """Set genelinde recall — kapının kendisi. Tek satırda ölçülür ki raporlanabilsin."""
    toplam = 0
    tutan = 0
    kacan: list[str] = []
    for case in CASES:
        subject_type = SubjectType(case["subject_type"])
        expected = normalize_name(case["canonical"], subject_type).sort_key
        for variant in case["variants"]:
            toplam += 1
            if normalize_name(variant, subject_type).sort_key == expected:
                tutan += 1
            else:
                kacan.append(f"[{case['id']}] {variant}")
    recall = tutan / toplam
    assert recall >= RECALL_FLOOR, (
        f"RECALL TABANI DÜŞTÜ: {recall:.3f} < {RECALL_FLOOR} "
        f"({toplam - tutan}/{toplam} varyant kaçtı)\n  " + "\n  ".join(kacan)
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [tuple(pair) for pair in DATASET["distinct_pairs"]],
    ids=[f"{pair[0]}|{pair[1]}" for pair in DATASET["distinct_pairs"]],
)
def test_farkli_varliklar_birlesmez(first: str, second: str) -> None:
    """Aşırı temizliğe karşı emniyet: farklı varlıklar aynı anahtara inmemeli.

    Recall tabanını "her şeyi sil, hepsi eşleşsin" diyerek geçmek mümkün olmamalı.
    """
    assert normalize_name(first).sort_key != normalize_name(second).sort_key
