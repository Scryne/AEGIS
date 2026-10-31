"""İzleme-lite fark çekirdeği (E2.4)."""

from __future__ import annotations

from aegis_core.monitoring.diff import CandidateView, diff_candidates


def cand(
    ext: str,
    decision: str = "pending",
    topics: tuple[str, ...] = (),
    auto: bool = False,
    subject: str = "s1",
) -> CandidateView:
    return CandidateView(subject, "Yıldız İnşaat", ext, f"Kayıt {ext}", 0.9, topics, decision, auto)


def test_identical_runs_produce_no_alert():
    run = [cand("A", "confirmed", ("sanction",)), cand("B", "dismissed")]
    assert diff_candidates(run, run).material is False


def test_new_match_is_reported_once():
    d = diff_candidates(
        [cand("A", "dismissed")], [cand("A", "dismissed"), cand("N", topics=("sanction",))]
    )
    assert [(i.kind, i.external_id) for i in d.items] == [("new_match", "N")]
    assert "sanction" in d.items[0].detail


def test_auto_dismissed_new_candidate_is_ignored():
    d = diff_candidates([], [cand("LOW", "dismissed", auto=True)])
    assert d.material is False


def test_human_dismissed_candidate_reappearing_is_not_new():
    d = diff_candidates([cand("FP", "dismissed")], [cand("FP", "pending")])
    assert d.items == []


def test_confirmed_match_disappearing_is_reported():
    d = diff_candidates([cand("A", "confirmed"), cand("B", "pending")], [])
    assert [(i.kind, i.external_id) for i in d.items] == [("removed_confirmed", "A")]


def test_topic_escalation_on_dismissed_record_is_reported_but_removal_is_not():
    up = diff_candidates(
        [cand("X", "dismissed", ("role.pep",))], [cand("X", "pending", ("role.pep", "sanction"))]
    )
    assert [(i.kind, i.topics_added) for i in up.items] == [("topics_changed", ("sanction",))]
    down = diff_candidates([cand("X", "dismissed", ("sanction",))], [cand("X", "pending", ())])
    assert down.items == []


def test_same_record_for_different_subjects_is_distinct():
    d = diff_candidates(
        [cand("A", "confirmed", subject="s1")], [cand("A", "confirmed", subject="s2")]
    )
    assert sorted(i.kind for i in d.items) == ["new_match", "removed_confirmed"]


def test_serializes():
    d = diff_candidates([], [cand("N")]).to_dict()
    assert d["items"][0]["kind"] == "new_match"
