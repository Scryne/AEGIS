"""Vaka yaşam döngüsü ve alarm derecesi saf çekirdekleri (E3.1/E3.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aegis_core.cases import lifecycle
from aegis_core.cases.lifecycle import CaseStatus, TransitionError, transition
from aegis_core.monitoring.severity import Severity, alert_severity, item_severity

REASON = "Kimlik ve doğum tarihi tutmuyor, yanlış pozitif."


def go(status: str, action: str, role: str = "compliance_officer", **kw: object) -> CaseStatus:
    opts: dict[str, object] = {"edd": False, "checklist_complete": False, "reason": REASON}
    opts.update(kw)
    return transition(status, action, role=role, **opts)  # type: ignore[arg-type]


# --- derece ---------------------------------------------------------------------------------


def test_new_sanction_match_is_critical() -> None:
    assert item_severity({"kind": "new_match", "topics_added": ["sanction"]}) is Severity.CRITICAL


def test_sanction_topic_added_to_existing_record_is_critical() -> None:
    item = {"kind": "topics_changed", "topics_added": ["sanction.linked"]}
    assert item_severity(item) is Severity.CRITICAL


def test_pep_and_removed_confirmed_are_high() -> None:
    assert item_severity({"kind": "new_match", "topics_added": ["role.pep"]}) is Severity.HIGH
    assert item_severity({"kind": "removed_confirmed", "topics_added": []}) is Severity.HIGH


def test_topicless_new_match_and_topic_drop_are_info() -> None:
    assert item_severity({"kind": "new_match", "topics_added": []}) is Severity.INFO
    dropped = {"kind": "topics_changed", "topics_added": [], "topics_removed": ["sanction"]}
    assert item_severity(dropped) is Severity.INFO


def test_alert_takes_highest_item() -> None:
    items = [
        {"kind": "new_match", "topics_added": []},
        {"kind": "removed_confirmed"},
        {"kind": "new_match", "topics_added": ["sanction"]},
    ]
    assert alert_severity(items) is Severity.CRITICAL
    assert alert_severity(items[:2]) is Severity.HIGH
    assert alert_severity([]) is Severity.INFO


# --- geçişler -------------------------------------------------------------------------------


def test_happy_path_new_review_approve_close() -> None:
    assert go("new", "start_review", role="analyst") is CaseStatus.IN_REVIEW
    assert go("in_review", "approve") is CaseStatus.APPROVED
    assert go("approved", "close") is CaseStatus.CLOSED
    assert go("closed", "reopen") is CaseStatus.IN_REVIEW


def test_analyst_can_escalate_but_cannot_decide() -> None:
    assert go("in_review", "escalate", role="analyst") is CaseStatus.ESCALATED
    for action in ("approve", "close"):
        with pytest.raises(TransitionError) as exc:
            go("in_review", action, role="analyst")
        assert exc.value.code == "forbidden"


def test_auditor_cannot_do_anything() -> None:
    for action in lifecycle.CaseAction:
        with pytest.raises(TransitionError) as exc:
            go("new", action.value, role="auditor")
        assert exc.value.code == "forbidden"


def test_invalid_source_state_is_rejected() -> None:
    with pytest.raises(TransitionError) as exc:
        go("new", "approve")
    assert exc.value.code == "invalid_state"
    with pytest.raises(TransitionError):
        go("closed", "escalate")


def test_decisions_need_a_reason() -> None:
    for action, src in (("approve", "in_review"), ("close", "in_review"), ("escalate", "new")):
        with pytest.raises(TransitionError) as exc:
            go(src, action, reason="kısa")
        assert exc.value.code == "reason_required"
    assert go("new", "start_review", reason=None) is CaseStatus.IN_REVIEW  # gerekçe istemez


def test_edd_case_needs_complete_checklist_to_approve_or_close() -> None:
    for action in ("approve", "close"):
        with pytest.raises(TransitionError) as exc:
            go("escalated", action, edd=True, checklist_complete=False)
        assert exc.value.code == "checklist_open"
        assert go("escalated", action, edd=True, checklist_complete=True) in (
            CaseStatus.APPROVED,
            CaseStatus.CLOSED,
        )
    # Onaylanmış bir vakanın kapanışı listeyi yeniden istemez (onayda denetlendi).
    assert go("approved", "close", edd=True, checklist_complete=False) is CaseStatus.CLOSED


def test_allowed_actions_follow_role_and_state() -> None:
    assert lifecycle.allowed_actions("new", role="analyst") == ["start_review", "escalate"]
    assert lifecycle.allowed_actions("in_review", role="compliance_officer") == [
        "escalate",
        "approve",
        "close",
    ]
    assert lifecycle.allowed_actions("closed", role="auditor") == []


def test_checklist_and_sla() -> None:
    items = lifecycle.new_checklist()
    assert len(items) == len(lifecycle.EDD_TEMPLATE)
    assert not lifecycle.checklist_complete(items)
    assert lifecycle.checklist_complete([{**i, "done": True} for i in items])
    assert not lifecycle.checklist_complete([])
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    assert lifecycle.due_at_for("critical", t0) == t0 + timedelta(days=2)
    assert lifecycle.due_at_for("bilinmeyen", t0) == t0 + timedelta(days=10)
    assert lifecycle.is_overdue("in_review", t0, t0 + timedelta(seconds=1))
    assert not lifecycle.is_overdue("closed", t0, t0 + timedelta(days=9))
    assert not lifecycle.is_overdue("new", None, t0)
