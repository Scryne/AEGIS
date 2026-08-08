"""Kural tabanlı risk özetinin birim testleri (E1.5).

Kurallar veritabanı bilmez; bu yüzden testler de bilmez. Buradaki iddialar ürünün
savunulabilirliğinin çekirdeğidir: hangi girdinin hangi seviyeyi doğurduğu ve —en az
onun kadar önemlisi— hangi girdinin seviyeyi doğurmadığı.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aegis_core.reports.risk import (
    CODE_DISCREPANCY_CRITICAL,
    CODE_DISCREPANCY_OPEN,
    CODE_MATCH_PENDING_FLAGGED,
    CODE_PEP_CONFIRMED,
    CODE_SANCTION_CONFIRMED,
    CODE_SCREENING_FAILED,
    CODE_SCREENING_MISSING,
    DiscrepancyView,
    MatchView,
    RiskLevel,
    ScreeningView,
    assess_risk,
)

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def _match(
    *,
    decision: str = "pending",
    topics: tuple[str, ...] = (),
    flagged: bool = False,
    score: float = 0.9,
) -> MatchView:
    return MatchView(
        subject_name="Özen Denetim A.Ş.",
        caption="OZEN DENETIM LTD",
        score=score,
        decision=decision,
        band="auto_flag" if flagged else "review",
        flagged=flagged,
        decided_automatically=False,
        topics=topics,
        datasets=("masak_dondurma",),
        source_url="https://example.org/kayit",
    )


def _completed(*matches: MatchView) -> ScreeningView:
    return ScreeningView(
        status="completed", completed_at=NOW, dataset="all", matches=tuple(matches)
    )


def _codes(assessment: object) -> set[str]:
    return {finding.code for finding in assessment.findings}  # type: ignore[attr-defined]


def test_onaylanmis_yaptirim_eslesmesi_yuksek_risk() -> None:
    result = assess_risk(
        screenings=[_completed(_match(decision="confirmed", topics=("sanction",)))]
    )
    assert result.level is RiskLevel.HIGH
    assert CODE_SANCTION_CONFIRMED in _codes(result)
    assert result.complete is True


@pytest.mark.parametrize("topic", ["sanction", "sanction.linked", "sanction.counter"])
def test_yaptirim_onekli_tum_konular_yaptirim_sayilir(topic: str) -> None:
    """``sanction.linked``/``sanction.counter`` de yaptırım bağlamıdır (yanlış negatif riski)."""
    result = assess_risk(screenings=[_completed(_match(decision="confirmed", topics=(topic,)))])
    assert result.level is RiskLevel.HIGH


def test_onaylanmis_pep_eslesmesi_artirilmis_risk() -> None:
    result = assess_risk(
        screenings=[_completed(_match(decision="confirmed", topics=("role.pep",)))]
    )
    assert result.level is RiskLevel.ELEVATED
    assert CODE_PEP_CONFIRMED in _codes(result)


def test_hem_yaptirim_hem_pep_ise_yaptirim_baskindir() -> None:
    result = assess_risk(
        screenings=[_completed(_match(decision="confirmed", topics=("role.pep", "sanction")))]
    )
    assert result.level is RiskLevel.HIGH
    assert CODE_SANCTION_CONFIRMED in _codes(result)
    assert CODE_PEP_CONFIRMED not in _codes(result)


def test_karar_bekleyen_yuksek_skorlu_eslesme_seviyeyi_yukseltmez() -> None:
    """Otomatik onay yoktur (ADR-0006): işaretli ama karara bağlanmamış eşleşme,
    dosyayı Yüksek yapmaz — yalnız "tamamlanmadı" der."""
    result = assess_risk(
        screenings=[_completed(_match(decision="pending", topics=("sanction",), flagged=True))]
    )
    assert result.level is RiskLevel.STANDARD
    assert result.complete is False
    assert CODE_MATCH_PENDING_FLAGGED in _codes(result)
    assert CODE_SANCTION_CONFIRMED not in _codes(result)


def test_elenen_eslesme_seviyeyi_etkilemez() -> None:
    result = assess_risk(
        screenings=[_completed(_match(decision="dismissed", topics=("sanction",)))]
    )
    assert result.level is RiskLevel.STANDARD
    assert result.complete is True


def test_temiz_kosu_standart_risktir() -> None:
    result = assess_risk(screenings=[_completed()])
    assert result.level is RiskLevel.STANDARD
    assert result.complete is True
    assert result.findings == ()


def test_hic_tarama_yoksa_seviye_belirsizdir() -> None:
    """ "Tarama yapılmadı" ile "tarama temiz çıktı" asla karıştırılmamalıdır."""
    result = assess_risk(screenings=[])
    assert result.level is RiskLevel.UNKNOWN
    assert result.complete is False
    assert CODE_SCREENING_MISSING in _codes(result)
    assert "temiz" in result.rationale.lower()


def test_basarisiz_kosu_temiz_degildir() -> None:
    result = assess_risk(
        screenings=[
            ScreeningView(
                status="failed", completed_at=None, dataset="all", error="yente erişilemedi"
            )
        ]
    )
    assert result.level is RiskLevel.UNKNOWN
    assert result.complete is False
    assert CODE_SCREENING_FAILED in _codes(result)


def test_basarisiz_kosu_yaninda_basarili_kosu_varsa_seviye_belirsiz_kalmaz() -> None:
    result = assess_risk(
        screenings=[
            ScreeningView(status="failed", completed_at=None, dataset="all", error="hata"),
            _completed(),
        ]
    )
    assert result.level is RiskLevel.STANDARD
    # Başarısız koşu yine de "işlem bekliyor" olarak görünür.
    assert result.complete is False
    assert CODE_SCREENING_FAILED in _codes(result)


def test_acik_kritik_tutarsizlik_artirilmis_risk() -> None:
    result = assess_risk(
        screenings=[_completed()],
        discrepancies=[
            DiscrepancyView(
                attribute_label="Vergi no",
                severity="critical",
                status="open",
                declared_value="1234567890",
                observed_value="9876543210",
            )
        ],
    )
    assert result.level is RiskLevel.ELEVATED
    assert result.complete is False
    assert CODE_DISCREPANCY_CRITICAL in _codes(result)


def test_acik_uyari_tutarsizligi_seviyeyi_yukseltmez_ama_isaretler() -> None:
    result = assess_risk(
        screenings=[_completed()],
        discrepancies=[
            DiscrepancyView(
                attribute_label="Adres",
                severity="warning",
                status="open",
                declared_value="Şişli/İstanbul",
                observed_value="Kadıköy/İstanbul",
            )
        ],
    )
    assert result.level is RiskLevel.STANDARD
    assert result.complete is False
    assert CODE_DISCREPANCY_OPEN in _codes(result)


@pytest.mark.parametrize("status", ["accepted", "resolved"])
def test_karara_baglanmis_tutarsizlik_seviyeyi_etkilemez(status: str) -> None:
    result = assess_risk(
        screenings=[_completed()],
        discrepancies=[
            DiscrepancyView(
                attribute_label="Vergi no",
                severity="critical",
                status=status,
                declared_value="1234567890",
                observed_value="9876543210",
            )
        ],
    )
    assert result.level is RiskLevel.STANDARD
    assert result.complete is True


def test_bilinen_bulgu_belirsizligi_bastirir() -> None:
    """Tarama koşmadı ama kritik tutarsızlık var: bilinen kötü, bilinmezden ağırdır."""
    result = assess_risk(
        screenings=[],
        discrepancies=[
            DiscrepancyView(
                attribute_label="Vergi no",
                severity="critical",
                status="open",
                declared_value="1",
                observed_value="2",
            )
        ],
    )
    assert result.level is RiskLevel.ELEVATED


def test_bulgular_seviyeye_gore_siralanir_ve_gerekce_tasir() -> None:
    result = assess_risk(
        screenings=[_completed(_match(decision="confirmed", topics=("sanction",)))],
        discrepancies=[
            DiscrepancyView(
                attribute_label="Adres",
                severity="warning",
                status="open",
                declared_value="a",
                observed_value="b",
            )
        ],
    )
    assert next(finding.code for finding in result.findings) == CODE_SANCTION_CONFIRMED
    # Her bulgu düz Türkçe, gösterilebilir bir gerekçe taşımalıdır.
    for finding in result.findings:
        assert len(finding.rationale) > 40
        assert finding.rationale.endswith(".")


def test_payload_jsonb_uyumludur() -> None:
    result = assess_risk(
        screenings=[_completed(_match(decision="confirmed", topics=("sanction",)))]
    )
    payload = result.to_payload()
    assert payload[0]["code"] == CODE_SANCTION_CONFIRMED
    assert payload[0]["level"] == "high"
    assert isinstance(payload[0]["source_refs"], list)
