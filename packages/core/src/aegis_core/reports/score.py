"""Açıklanabilir risk puanı (E2.3) — ağırlıklı faktör modeli, saf çekirdek.

ADR-0008 risk *seviyesini* kural olarak tanımladı ve puanı Phase 2'ye bıraktı. Bu modül o
puandır, ama aynı savunulabilirlik ölçütüyle: her puan, toplamı oluşturan faktörlerin listesi
olarak gelir; her faktör gerekçesini ve dayandığı kaydı (tarama adayı, tutarsızlık, UBO
hesabı) taşır. "Bu dosyaya neden 45 dediniz" sorusunun cevabı faktör tablosudur.

Kurallar (plan §6.6):

* Yalnız **yapılandırılmış bulgular** puanlanır: onaylanmış eşleşmeler, açık tutarsızlıklar,
  UBO belirlenebilirliği, tarama durumu, yargı alanı. LLM çıktısı hiçbir zaman doğrudan puan
  vermez (olumsuz haber betası E3.6'ya kadar puan dışıdır).
* Ağırlıklar **sabittir** (``WEIGHTS_VERSION``); kiracı bazında ayar müşteri isteyene kadar yok.
  Ağırlık değişirse sürüm değişir ve eski anlık görüntüler eski sürümle okunur.
* Puan 0–100 arasında kırpılır. Onaylanmış yaptırım eşleşmesi puandan bağımsız olarak bandı
  **yüksek** yapar: toplamın altında kalan bir yaptırım "orta risk" olarak okunamaz.
* Karar bekleyen bulgular puana küçük bir pay katar ve ``complete=False`` yapar; seviyede olduğu
  gibi (ADR-0008 §2) bekleyen eşleşme dosyayı yüksek riske taşımaz.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from aegis_core.reports.risk import (
    CODE_DISCREPANCY_CRITICAL,
    CODE_DISCREPANCY_OPEN,
    CODE_MATCH_CONFIRMED_OTHER,
    CODE_MATCH_PENDING,
    CODE_MATCH_PENDING_FLAGGED,
    CODE_PEP_CONFIRMED,
    CODE_SANCTION_CONFIRMED,
    CODE_SCREENING_FAILED,
    CODE_SCREENING_MISSING,
    RiskAssessment,
)

WEIGHTS_VERSION = "v1"


class ScoreBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


BAND_LABELS = {ScoreBand.LOW: "Düşük", ScoreBand.MEDIUM: "Orta", ScoreBand.HIGH: "Yüksek"}

# Bant sınırları (v1): 0–24 düşük, 25–49 orta, 50+ yüksek.
MEDIUM_FROM = 25
HIGH_FROM = 50


@dataclass(frozen=True)
class Weight:
    points: int
    cap: int
    """Aynı faktör birden çok kez görülürse toplam katkının tavanı."""
    label: str


# v1 ağırlıkları ve gerekçesi (ADR-0010):
#  - Yaptırım tek başına yüksek bandı açar (60); PEP artırılmış inceleme gerektirir ama tek başına
#    yüksek değildir (25).
#  - UBO'nun belirlenememesi MASAK açısından kendi başına bir işarettir (20); hesap hiç yapılmamışsa
#    dosya eksiktir (10).
#  - Kritik kimlik tutarsızlığı, beyanın güvenilirliğini düşürür (15/adet, tavan 30).
WEIGHTS: dict[str, Weight] = {
    CODE_SANCTION_CONFIRMED: Weight(60, 60, "Onaylanmış yaptırım eşleşmesi"),
    CODE_PEP_CONFIRMED: Weight(25, 25, "Onaylanmış PEP eşleşmesi"),
    CODE_MATCH_CONFIRMED_OTHER: Weight(15, 15, "Onaylanmış diğer liste eşleşmesi"),
    CODE_MATCH_PENDING_FLAGGED: Weight(8, 16, "Karar bekleyen işaretli eşleşme"),
    CODE_MATCH_PENDING: Weight(2, 6, "Karar bekleyen eşleşme"),
    CODE_DISCREPANCY_CRITICAL: Weight(15, 30, "Açık kritik tutarsızlık"),
    CODE_DISCREPANCY_OPEN: Weight(5, 10, "Açık tutarsızlık"),
    CODE_SCREENING_FAILED: Weight(10, 10, "Başarısız tarama koşusu"),
    CODE_SCREENING_MISSING: Weight(15, 15, "Tarama yapılmadı"),
    "ubo.not_determinable": Weight(20, 20, "Gerçek faydalanıcı belirlenemedi"),
    "ubo.none_found": Weight(10, 10, "Eşiği aşan gerçek faydalanıcı yok"),
    "ubo.cycle": Weight(5, 5, "Döngüsel ortaklık yapısı"),
    "ubo.missing": Weight(10, 10, "Gerçek faydalanıcı hesabı yapılmadı"),
    "jurisdiction.foreign": Weight(5, 5, "Yabancı yargı alanında kurulu"),
    "jurisdiction.high_risk": Weight(20, 20, "Yüksek riskli yargı alanı"),
}


@dataclass(frozen=True)
class UboView:
    computation_id: str
    status: str
    cycles: int
    unresolved: int


@dataclass(frozen=True)
class ScoreFactor:
    code: str
    label: str
    points: int
    occurrences: int
    reason: str
    evidence: tuple[str, ...] = ()
    """Dayanak kayıtlar: ``screening:<id>``, ``match:<id>``, ``ubo:<id>``, ``entity:<id>`` …"""


@dataclass(frozen=True)
class RiskScore:
    score: int
    band: ScoreBand
    factors: tuple[ScoreFactor, ...]
    complete: bool
    weights_version: str = WEIGHTS_VERSION
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "band": self.band.value,
            "band_label": BAND_LABELS[self.band],
            "complete": self.complete,
            "weights_version": self.weights_version,
            "notes": list(self.notes),
            "factors": [
                {
                    "code": f.code,
                    "label": f.label,
                    "points": f.points,
                    "occurrences": f.occurrences,
                    "reason": f.reason,
                    "evidence": list(f.evidence),
                }
                for f in self.factors
            ],
        }


def _band(score: int) -> ScoreBand:
    if score >= HIGH_FROM:
        return ScoreBand.HIGH
    if score >= MEDIUM_FROM:
        return ScoreBand.MEDIUM
    return ScoreBand.LOW


def score_risk(
    assessment: RiskAssessment,
    *,
    entity_id: str,
    schema_type: str,
    country: str | None,
    ubo: UboView | None,
    high_risk_countries: Sequence[str] = (),
) -> RiskScore:
    """Kural bulgularından ve UBO/yargı alanı sinyallerinden faktörlü puan üretir."""
    grouped: dict[str, list[tuple[str, tuple[str, ...]]]] = {}

    def add(code: str, reason: str, evidence: tuple[str, ...] = ()) -> None:
        grouped.setdefault(code, []).append((reason, evidence))

    for finding in assessment.findings:
        if finding.code in WEIGHTS:
            add(finding.code, finding.rationale, tuple(finding.source_refs))

    if schema_type == "Company":
        if ubo is None:
            add("ubo.missing", "Şirket için gerçek faydalanıcı hesabı henüz yapılmadı.")
        else:
            ref = (f"ubo:{ubo.computation_id}",)
            if ubo.status == "not_determinable":
                add(
                    "ubo.not_determinable",
                    f"Son UBO hesabında {ubo.unresolved} çözülemeyen zincir halkası ya da "
                    "döngüde kalan pay eşiği aşabiliyor.",
                    ref,
                )
            elif ubo.status == "none_found":
                add(
                    "ubo.none_found",
                    "Zincir çözüldü ama eşiği aşan, kontrol eden ya da yönetici kişi yok.",
                    ref,
                )
            if ubo.cycles:
                add("ubo.cycle", f"Ortaklık yapısında {ubo.cycles} döngü var.", ref)

    code = (country or "").upper()
    if code and code in {c.upper() for c in high_risk_countries}:
        add(
            "jurisdiction.high_risk",
            f"Kuruluş/ikamet ülkesi ({code}) yüksek riskli listede.",
            (f"entity:{entity_id}",),
        )
    elif code and code not in ("TR", "TUR") and schema_type == "Company":
        add(
            "jurisdiction.foreign",
            f"Şirket {code} yargı alanında kurulu.",
            (f"entity:{entity_id}",),
        )

    factors: list[ScoreFactor] = []
    for code_key, items in grouped.items():
        weight = WEIGHTS[code_key]
        points = min(weight.points * len(items), weight.cap)
        evidence = tuple(dict.fromkeys(ref for _, refs in items for ref in refs))
        reason = (
            items[0][0] if len(items) == 1 else f"{items[0][0]} (+{len(items) - 1} benzer bulgu)"
        )
        factors.append(ScoreFactor(code_key, weight.label, points, len(items), reason, evidence))
    factors.sort(key=lambda f: (-f.points, f.code))

    score = min(100, sum(f.points for f in factors))
    band = _band(score)
    notes: list[str] = []
    if any(f.code == CODE_SANCTION_CONFIRMED for f in factors):
        band = ScoreBand.HIGH
        notes.append("Onaylanmış yaptırım eşleşmesi bandı puandan bağımsız olarak yüksek yapar.")
    return RiskScore(
        score=score,
        band=band,
        factors=tuple(factors),
        complete=assessment.complete,
        notes=tuple(notes),
    )
