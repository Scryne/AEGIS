"""Tarama eşik bandı testleri (E1.3).

Kritik davranış: yüksek skorlu bir aday **otomatik onaylanmaz**. Otomatik onay,
"karar desteği" ürününü sessizce "karar veren" ürüne çevirirdi (Ürün Planı §3.3).
"""

from __future__ import annotations

import pytest

from aegis_core.screening.thresholds import (
    DEFAULT_THRESHOLDS,
    MatchBand,
    MatchDecision,
    ScreeningThresholds,
)


def test_varsayilan_bantlar_tutarlidir() -> None:
    assert DEFAULT_THRESHOLDS.candidate_cutoff <= DEFAULT_THRESHOLDS.auto_dismiss_below
    assert DEFAULT_THRESHOLDS.auto_dismiss_below <= DEFAULT_THRESHOLDS.auto_flag_at


@pytest.mark.parametrize(
    ("score", "band", "decision"),
    [
        (0.10, MatchBand.AUTO_DISMISS, MatchDecision.DISMISSED),
        (0.64, MatchBand.AUTO_DISMISS, MatchDecision.DISMISSED),
        (0.65, MatchBand.REVIEW, MatchDecision.PENDING),
        (0.80, MatchBand.REVIEW, MatchDecision.PENDING),
        (0.85, MatchBand.AUTO_FLAG, MatchDecision.PENDING),
        (1.00, MatchBand.AUTO_FLAG, MatchDecision.PENDING),
    ],
)
def test_bant_sinirlari(score: float, band: MatchBand, decision: MatchDecision) -> None:
    disposition = DEFAULT_THRESHOLDS.disposition(score)
    assert disposition.band is band
    assert disposition.decision is decision


def test_yuksek_skor_otomatik_onaylanmaz() -> None:
    """En yüksek skor bile insan onayı bekler; yalnız işaretlenir."""
    disposition = DEFAULT_THRESHOLDS.disposition(1.0)
    assert disposition.decision is MatchDecision.PENDING
    assert disposition.flagged is True
    assert disposition.auto is False


def test_dusuk_skor_otomatik_elenir_ve_isaretlenmez() -> None:
    disposition = DEFAULT_THRESHOLDS.disposition(0.2)
    assert disposition.decision is MatchDecision.DISMISSED
    assert disposition.auto is True
    assert disposition.flagged is False


def test_ayardan_yukleme() -> None:
    thresholds = ScreeningThresholds.from_mapping(
        {"auto_dismiss_below": 0.7, "auto_flag_at": 0.9, "candidate_cutoff": 0.6}
    )
    assert thresholds.auto_dismiss_below == 0.7
    assert thresholds.disposition(0.65).decision is MatchDecision.DISMISSED


def test_bos_ayar_varsayilana_duser() -> None:
    assert ScreeningThresholds.from_mapping(None) == DEFAULT_THRESHOLDS
    assert ScreeningThresholds.from_mapping({}) == DEFAULT_THRESHOLDS


def test_yazim_hatasi_sessizce_yok_sayilmaz() -> None:
    """Tanınmayan anahtar hata verir: kiracı ayarladığını sandığı eşikle çalışmamalı."""
    with pytest.raises(ValueError, match="Tanınmayan eşik anahtarı"):
        ScreeningThresholds.from_mapping({"auto_dismis_below": 0.7})


@pytest.mark.parametrize(
    "raw",
    [
        {"auto_dismiss_below": 1.5},
        {"auto_flag_at": -0.1},
        {"auto_dismiss_below": 0.9, "auto_flag_at": 0.5},
        {"candidate_cutoff": 0.9, "auto_dismiss_below": 0.6},
    ],
)
def test_tutarsiz_esikler_reddedilir(raw: dict[str, float]) -> None:
    with pytest.raises(ValueError, match=r"olamaz|olmalıdır"):
        ScreeningThresholds.from_mapping(raw)


def test_to_mapping_round_trip() -> None:
    """Koşuya gömülen anlık görüntü geri yüklenebilmelidir (derin koşu bunu kullanır)."""
    original = ScreeningThresholds(auto_dismiss_below=0.7, auto_flag_at=0.95, candidate_cutoff=0.55)
    assert ScreeningThresholds.from_mapping(original.to_mapping()) == original
