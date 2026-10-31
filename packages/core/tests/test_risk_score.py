"""Açıklanabilir risk puanı (E2.3): faktörler, tavanlar, bantlar, yaptırım, UBO sinyalleri."""

from __future__ import annotations

from aegis_core.reports.risk import (
    CODE_DISCREPANCY_CRITICAL,
    CODE_PEP_CONFIRMED,
    CODE_SANCTION_CONFIRMED,
    CODE_SCREENING_MISSING,
    RiskAssessment,
    RiskFinding,
    RiskLevel,
)
from aegis_core.reports.score import ScoreBand, UboView, score_risk


def assessment(*codes: str, complete: bool = True) -> RiskAssessment:
    findings = tuple(
        RiskFinding(code=c, title=c, rationale=f"gerekçe {c}", source_refs=(f"match:{i}",))
        for i, c in enumerate(codes)
    )
    return RiskAssessment(
        level=RiskLevel.STANDARD, rationale="", findings=findings, complete=complete
    )


UBO_OK = UboView("u1", "determined", cycles=0, unresolved=0)


def test_clean_company_scores_zero():
    s = score_risk(assessment(), entity_id="e", schema_type="Company", country="TR", ubo=UBO_OK)
    assert s.score == 0
    assert s.band is ScoreBand.LOW
    assert s.factors == ()


def test_every_factor_carries_reason_and_evidence():
    s = score_risk(
        assessment(CODE_PEP_CONFIRMED),
        entity_id="e",
        schema_type="Company",
        country="TR",
        ubo=UBO_OK,
    )
    (f,) = s.factors
    assert (f.code, f.points, f.evidence) == (CODE_PEP_CONFIRMED, 25, ("match:0",))
    assert f.reason == "gerekçe pep.confirmed"
    assert s.band is ScoreBand.MEDIUM


def test_repeated_findings_are_capped():
    codes = [CODE_DISCREPANCY_CRITICAL] * 4
    s = score_risk(assessment(*codes), entity_id="e", schema_type="Person", country=None, ubo=None)
    (f,) = s.factors
    assert f.points == 30
    assert f.occurrences == 4
    assert "+3 benzer" in f.reason


def test_sanction_forces_high_band_and_score_is_clamped():
    s = score_risk(
        assessment(
            CODE_SANCTION_CONFIRMED,
            CODE_PEP_CONFIRMED,
            CODE_DISCREPANCY_CRITICAL,
            CODE_DISCREPANCY_CRITICAL,
        ),
        entity_id="e",
        schema_type="Company",
        country="IR",
        ubo=UboView("u9", "not_determinable", cycles=1, unresolved=2),
        high_risk_countries=["IR"],
    )
    assert s.score == 100
    assert s.band is ScoreBand.HIGH
    assert s.notes


def test_sanction_alone_is_high_even_below_threshold():
    # 60 puan zaten yüksek; tek başına yüksek bandı açtığını açıkça doğrular.
    s = score_risk(
        assessment(CODE_SANCTION_CONFIRMED),
        entity_id="e",
        schema_type="Person",
        country="TR",
        ubo=None,
    )
    assert s.band is ScoreBand.HIGH


def test_ubo_signals_for_companies_only():
    missing = score_risk(assessment(), entity_id="e", schema_type="Company", country="TR", ubo=None)
    assert [f.code for f in missing.factors] == ["ubo.missing"]
    person = score_risk(assessment(), entity_id="e", schema_type="Person", country="TR", ubo=None)
    assert person.factors == ()

    unclear = score_risk(
        assessment(),
        entity_id="e",
        schema_type="Company",
        country="TR",
        ubo=UboView("u2", "not_determinable", cycles=1, unresolved=1),
    )
    assert {f.code: f.points for f in unclear.factors} == {
        "ubo.not_determinable": 20,
        "ubo.cycle": 5,
    }
    assert all(f.evidence == ("ubo:u2",) for f in unclear.factors)


def test_jurisdiction_factors():
    foreign = score_risk(
        assessment(), entity_id="e1", schema_type="Company", country="NL", ubo=UBO_OK
    )
    assert [(f.code, f.evidence) for f in foreign.factors] == [
        ("jurisdiction.foreign", ("entity:e1",))
    ]
    listed = score_risk(
        assessment(),
        entity_id="e1",
        schema_type="Company",
        country="nl",
        ubo=UBO_OK,
        high_risk_countries=["NL"],
    )
    assert [f.code for f in listed.factors] == ["jurisdiction.high_risk"]


def test_incomplete_assessment_propagates_and_missing_screening_counts():
    s = score_risk(
        assessment(CODE_SCREENING_MISSING, complete=False),
        entity_id="e",
        schema_type="Person",
        country="TR",
        ubo=None,
    )
    assert s.complete is False
    assert s.score == 15


def test_serialization_is_stable():
    s = score_risk(
        assessment(CODE_PEP_CONFIRMED), entity_id="e", schema_type="Person", country="TR", ubo=None
    )
    d = s.to_dict()
    assert d["weights_version"] == "v1"
    assert d["band_label"] == "Orta"
    assert (
        d
        == score_risk(
            assessment(CODE_PEP_CONFIRMED),
            entity_id="e",
            schema_type="Person",
            country="TR",
            ubo=None,
        ).to_dict()
    )
