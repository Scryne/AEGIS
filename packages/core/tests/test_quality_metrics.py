"""Eşleşme kalitesi metrikleri (E3.6)."""

from __future__ import annotations

from aegis_core.quality.metrics import (
    MIN_LABELS,
    Label,
    MediaLabel,
    adverse_media_precision,
    evaluate,
    recommend,
    sweep,
)


def L(score: float, decision: str, automatic: bool = False) -> Label:  # noqa: N802
    return Label(score, decision, automatic)


def test_rates_and_flag_precision_recall() -> None:
    labels = [
        L(0.95, "confirmed"),
        L(0.90, "dismissed"),
        L(0.70, "confirmed"),
        L(0.68, "dismissed"),
        L(0.60, "dismissed", automatic=True),  # doğrusu bilinmez: metriğe girmez
        L(0.80, "pending"),
    ]
    q = evaluate(labels, auto_dismiss_below=0.65, auto_flag_at=0.85)
    assert (q.total, q.auto_dismissed, q.pending, q.confirmed, q.dismissed) == (6, 1, 1, 2, 2)
    assert q.false_positive_rate == 0.5
    assert q.review_rate == round(5 / 6, 4)  # 4 kararlı + 1 bekleyen / 6
    assert (q.flagged_decided, q.flagged_confirmed) == (2, 1)
    assert q.flag_precision == 0.5
    assert q.flag_recall == 0.5  # onaylı 0.70 işaret eşiğinin altında kaldı
    assert q.min_confirmed_score == 0.7


def test_empty_set_has_no_rates() -> None:
    q = evaluate([], auto_dismiss_below=0.65, auto_flag_at=0.85)
    assert q.false_positive_rate is None
    assert q.review_rate is None
    assert q.recommendation is not None
    assert q.recommendation["status"] == "insufficient"


def test_sweep_counts_lost_confirmed() -> None:
    human = [L(0.72, "confirmed"), L(0.55, "dismissed"), L(0.66, "dismissed")]
    rows = {r["threshold"]: r for r in sweep(human, current=0.65)}
    assert rows[0.6]["saved_reviews"] == 1
    assert rows[0.6]["lost_confirmed"] == 0
    assert rows[0.675]["saved_reviews"] == 2
    assert rows[0.75]["lost_confirmed"] == 1
    assert rows[0.65]["current"] is True


def test_recommendation_never_loses_a_confirmed_match() -> None:
    human = [L(0.82, "confirmed")] + [L(0.52 + 0.01 * i, "dismissed") for i in range(MIN_LABELS)]
    rec = recommend(human, current=0.65, auto_flag_at=0.85)
    assert rec["status"] == "raise"
    assert rec["threshold"] == 0.77  # en düşük onaylı 0.82 − 0.05 pay
    assert all(not (h.decision == "confirmed" and h.score < rec["threshold"]) for h in human)
    assert rec["saved_reviews"] == sum(
        1 for h in human if h.decision == "dismissed" and h.score < 0.77
    )


def test_recommendation_capped_below_flag_and_keep_when_no_room() -> None:
    many = [L(0.5 + 0.001 * i, "dismissed") for i in range(MIN_LABELS)]
    capped = recommend([*many, L(0.99, "confirmed")], current=0.65, auto_flag_at=0.85)
    assert capped["threshold"] == 0.8  # işaret eşiğinin altında kalır
    tight = recommend([*many, L(0.66, "confirmed")], current=0.65, auto_flag_at=0.85)
    assert tight["status"] == "keep"


def test_recommendation_needs_enough_labels() -> None:
    few = [L(0.9, "confirmed")] * (MIN_LABELS - 1)
    assert recommend(few, current=0.65, auto_flag_at=0.85)["status"] == "insufficient"


def test_adverse_media_precision() -> None:
    items = [
        MediaLabel("ilgili", True),
        MediaLabel("ilgisiz", True),
        MediaLabel("ilgisiz", False),
        MediaLabel("aday", True),
    ]
    m = adverse_media_precision(items)
    assert (m["candidates"], m["reviewed"], m["relevant"]) == (4, 3, 1)
    assert m["precision"] == round(1 / 3, 4)
    assert m["hint_precision"] == 0.5
    assert m["promotion_ready"] is False
