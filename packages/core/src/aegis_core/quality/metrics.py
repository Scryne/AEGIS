"""Eşleşme kalitesi ölçümü (E3.6, ADR-0017) — saf çekirdek.

Etiket = insanın kararı. ``decided_automatically=False`` ve ``confirmed`` olan aday gerçek
eşleşme, ``dismissed`` olan yanlış pozitiftir. Motorun otomatik elediği adayların doğrusu
**bilinmez** (insan görmedi); sayıları ayrıca raporlanır, metriğe katılmaz. Bu bilinçli bir
sınırdır: otomatik eleme bandında kaçan gerçek eşleşme bu yöntemle görülemez;
onu E1.3'ün recall seti ölçer.

Ölçülenler:

* **Yanlış pozitif oranı** — insanın elediği / insanın karar verdiği.
* **İnceleme oranı** — insan kararı gereken aday / toplam aday (otomatik elenenler dahil).
* **İşaretleme isabeti** — ``auto_flag_at`` üstündeki kararlı adayların onaylanan payı
  (precision) ve onaylananların işaretlenmiş payı (recall).
* **Eşik taraması** — her aday eşik için: bu eşiğin altını otomatik elesek kaç insan kararı
  azalırdı ve **kaç onaylı eşleşme kaybolurdu**. Öneri, kayıp sıfırken ulaşılabilen en yüksek
  eşikten bir güvenlik payı aşağıdadır. Öneri bir **öneridir**: eşiği uyum uzmanı değiştirir.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

MIN_LABELS = 30
"""Bu sayının altında öneri verilmez: az etiketle eşik oynatmak gürültüyü ayar sanmaktır."""

SAFETY_MARGIN = 0.05
SWEEP = tuple(round(0.50 + 0.025 * i, 3) for i in range(19))  # 0.50 … 0.95


@dataclass(frozen=True)
class Label:
    score: float
    decision: str  # confirmed | dismissed | pending
    automatic: bool


@dataclass
class MatchQuality:
    total: int = 0
    auto_dismissed: int = 0
    pending: int = 0
    confirmed: int = 0
    dismissed: int = 0
    flagged_decided: int = 0
    flagged_confirmed: int = 0
    false_positive_rate: float | None = None
    review_rate: float | None = None
    flag_precision: float | None = None
    flag_recall: float | None = None
    min_confirmed_score: float | None = None
    sweep: list[dict[str, Any]] = field(default_factory=list)
    recommendation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def evaluate(
    labels: Iterable[Label], *, auto_dismiss_below: float, auto_flag_at: float
) -> MatchQuality:
    rows = list(labels)
    q = MatchQuality(total=len(rows))
    human = [r for r in rows if not r.automatic and r.decision in ("confirmed", "dismissed")]
    q.auto_dismissed = sum(1 for r in rows if r.automatic and r.decision == "dismissed")
    q.pending = sum(1 for r in rows if r.decision == "pending")
    q.confirmed = sum(1 for r in human if r.decision == "confirmed")
    q.dismissed = sum(1 for r in human if r.decision == "dismissed")
    flagged = [r for r in human if r.score >= auto_flag_at]
    q.flagged_decided = len(flagged)
    q.flagged_confirmed = sum(1 for r in flagged if r.decision == "confirmed")

    q.false_positive_rate = _ratio(q.dismissed, len(human))
    q.review_rate = _ratio(len(human) + q.pending, q.total)
    q.flag_precision = _ratio(q.flagged_confirmed, q.flagged_decided)
    q.flag_recall = _ratio(q.flagged_confirmed, q.confirmed)
    confirmed_scores = [r.score for r in human if r.decision == "confirmed"]
    q.min_confirmed_score = round(min(confirmed_scores), 4) if confirmed_scores else None

    q.sweep = sweep(human, current=auto_dismiss_below)
    q.recommendation = recommend(human, current=auto_dismiss_below, auto_flag_at=auto_flag_at)
    return q


def sweep(human: Sequence[Label], *, current: float) -> list[dict[str, Any]]:
    """Her aday eşik için: altını otomatik elesek ne olurdu."""
    out = []
    for t in SWEEP:
        below = [r for r in human if r.score < t]
        out.append(
            {
                "threshold": t,
                "saved_reviews": sum(1 for r in below if r.decision == "dismissed"),
                "lost_confirmed": sum(1 for r in below if r.decision == "confirmed"),
                "current": abs(t - current) < 1e-9,
            }
        )
    return out


def recommend(human: Sequence[Label], *, current: float, auto_flag_at: float) -> dict[str, Any]:
    """Otomatik eleme eşiği önerisi; yeterli etiket yoksa nedenini söyler."""
    if len(human) < MIN_LABELS:
        return {
            "status": "insufficient",
            "message": f"Öneri için en az {MIN_LABELS} insan kararı gerekir (şu an {len(human)}).",
        }
    confirmed = [r.score for r in human if r.decision == "confirmed"]
    ceiling = min(confirmed) if confirmed else auto_flag_at
    target = round(max(0.0, min(ceiling - SAFETY_MARGIN, auto_flag_at - SAFETY_MARGIN)), 3)
    saved = sum(1 for r in human if r.decision == "dismissed" and r.score < target)
    if target <= current + 1e-9:
        return {
            "status": "keep",
            "threshold": current,
            "message": "Geçmiş kararlar mevcut eşiği yükseltmeye güvenli alan bırakmıyor.",
        }
    return {
        "status": "raise",
        "threshold": target,
        "saved_reviews": saved,
        "message": (
            f"Onaylanan en düşük skor {ceiling:.2f}. Otomatik eleme eşiği {target:.2f}'ye "
            f"çıkarılırsa geçmişte {saved} gereksiz inceleme olmazdı, onaylı eşleşme kaybolmazdı "
            f"(güvenlik payı {SAFETY_MARGIN:.2f})."
        ),
    }


@dataclass(frozen=True)
class MediaLabel:
    status: str  # aday | ilgili | ilgisiz
    has_negative_term: bool


def adverse_media_precision(items: Iterable[MediaLabel]) -> dict[str, Any]:
    """Olumsuz haber betası: insan ayıklamasına göre isabet (puana alınma kararının girdisi)."""
    rows = list(items)
    reviewed = [r for r in rows if r.status in ("ilgili", "ilgisiz")]
    relevant = [r for r in reviewed if r.status == "ilgili"]
    hinted = [r for r in reviewed if r.has_negative_term]
    hinted_relevant = [r for r in hinted if r.status == "ilgili"]
    return {
        "candidates": len(rows),
        "reviewed": len(reviewed),
        "relevant": len(relevant),
        "precision": _ratio(len(relevant), len(reviewed)),
        "hint_precision": _ratio(len(hinted_relevant), len(hinted)),
        "promotion_ready": len(reviewed) >= 100
        and (_ratio(len(relevant), len(reviewed)) or 0) >= 0.8,
    }
