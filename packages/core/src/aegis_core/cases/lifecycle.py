"""Vaka yaşam döngüsü (E3.2) — saf durum makinesi, veritabanı ve ağ bilmez.

ROADMAP E3.2: *"new → in review → approved / escalated (EDD) → closed; assignment, due dates,
comments"*. Geçişler:

=============  ==========================  ===============================  ====================
Eylem          Kaynak durum                Hedef                            Kim
=============  ==========================  ===============================  ====================
start_review   new                         in_review                        owner · CO · analyst
escalate       new · in_review             escalated (EDD açılır)           owner · CO · analyst
approve        in_review · escalated       approved                         owner · CO
close          in_review · escalated ·     closed                           owner · CO
               approved
reopen         approved · closed           in_review                        owner · CO
=============  ==========================  ===============================  ====================

* Analist dosyayı hazırlar ve riski **yükseltebilir** (escalate) ama karar veremez: onay ve
  kapanış uyum görevlisinindir (``Role`` tanımıyla aynı ayrım). Denetçi hiçbir geçiş yapamaz.
* EDD açık bir vaka, kontrol listesi tamamlanmadan onaylanamaz ve kapatılamaz.
* Karar gerektiren geçişler (approve, close, reopen) gerekçe ister; gerekçe denetim izine yazılır.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any


class CaseStatus(StrEnum):
    NEW = "new"
    IN_REVIEW = "in_review"
    ESCALATED = "escalated"
    APPROVED = "approved"
    CLOSED = "closed"


class CaseAction(StrEnum):
    START_REVIEW = "start_review"
    ESCALATE = "escalate"
    APPROVE = "approve"
    CLOSE = "close"
    REOPEN = "reopen"


class CaseSource(StrEnum):
    MANUAL = "manual"
    MONITORING_ALERT = "monitoring_alert"
    SCREENING = "screening"


STATUS_LABELS: dict[CaseStatus, str] = {
    CaseStatus.NEW: "Yeni",
    CaseStatus.IN_REVIEW: "İncelemede",
    CaseStatus.ESCALATED: "Sıkılaştırılmış inceleme (EDD)",
    CaseStatus.APPROVED: "Onaylandı",
    CaseStatus.CLOSED: "Kapandı",
}

OPEN_STATUSES = frozenset({CaseStatus.NEW, CaseStatus.IN_REVIEW, CaseStatus.ESCALATED})

WRITER_ROLES = frozenset({"owner", "compliance_officer", "analyst"})
DECIDER_ROLES = frozenset({"owner", "compliance_officer"})

MIN_REASON_LEN = 10


@dataclass(frozen=True)
class _Rule:
    sources: frozenset[CaseStatus]
    target: CaseStatus
    roles: frozenset[str]
    needs_reason: bool
    needs_checklist_if_edd: bool


RULES: dict[CaseAction, _Rule] = {
    CaseAction.START_REVIEW: _Rule(
        frozenset({CaseStatus.NEW}), CaseStatus.IN_REVIEW, WRITER_ROLES, False, False
    ),
    CaseAction.ESCALATE: _Rule(
        frozenset({CaseStatus.NEW, CaseStatus.IN_REVIEW}),
        CaseStatus.ESCALATED,
        WRITER_ROLES,
        True,
        False,
    ),
    CaseAction.APPROVE: _Rule(
        frozenset({CaseStatus.IN_REVIEW, CaseStatus.ESCALATED}),
        CaseStatus.APPROVED,
        DECIDER_ROLES,
        True,
        True,
    ),
    CaseAction.CLOSE: _Rule(
        frozenset({CaseStatus.IN_REVIEW, CaseStatus.ESCALATED, CaseStatus.APPROVED}),
        CaseStatus.CLOSED,
        DECIDER_ROLES,
        True,
        True,
    ),
    CaseAction.REOPEN: _Rule(
        frozenset({CaseStatus.APPROVED, CaseStatus.CLOSED}),
        CaseStatus.IN_REVIEW,
        DECIDER_ROLES,
        True,
        False,
    ),
}


class TransitionError(Exception):
    """Geçiş kurallara aykırı. ``code`` API'de hata kodunu seçer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code  # "forbidden" | "invalid_state" | "reason_required" | "checklist_open"
        self.message = message


def transition(
    status: str,
    action: str,
    *,
    role: str,
    edd: bool,
    checklist_complete: bool,
    reason: str | None,
) -> CaseStatus:
    """Kuralları uygular; geçerliyse hedef durumu döner, değilse ``TransitionError``."""
    try:
        act = CaseAction(action)
    except ValueError as exc:
        raise TransitionError("invalid_state", f"Bilinmeyen eylem: {action}") from exc
    rule = RULES[act]
    if role not in rule.roles:
        raise TransitionError("forbidden", "Bu geçiş için yetkiniz yok.")
    current = CaseStatus(status)
    if current not in rule.sources:
        raise TransitionError(
            "invalid_state",
            f"'{STATUS_LABELS[current]}' durumundaki vakaya bu eylem uygulanamaz.",
        )
    if rule.needs_reason and len((reason or "").strip()) < MIN_REASON_LEN:
        raise TransitionError("reason_required", f"Gerekçe en az {MIN_REASON_LEN} karakter olmalı.")
    # Kapanış onaylı bir vakadan geliyorsa liste zaten onayda denetlendi.
    needs_list = rule.needs_checklist_if_edd and edd and current != CaseStatus.APPROVED
    if needs_list and not checklist_complete:
        raise TransitionError(
            "checklist_open", "EDD kontrol listesi tamamlanmadan bu karar verilemez."
        )
    return rule.target


def allowed_actions(status: str, *, role: str) -> list[str]:
    """Arayüzün göstereceği eylemler (gerekçe/liste koşulları hariç, yalnız durum + rol)."""
    current = CaseStatus(status)
    return [a.value for a, r in RULES.items() if current in r.sources and role in r.roles]


# --- EDD kontrol listesi --------------------------------------------------------------------

EDD_TEMPLATE_VERSION = "edd-sablon-v1"
"""Şablon sürümü vaka satırına yazılır; şablon değişirse eski vakalar kendi sürümünü korur."""

EDD_TEMPLATE: tuple[tuple[str, str], ...] = (
    ("match_evidence", "Eşleşme kararı kanıtıyla belgelendi (kimlik, doğum tarihi/sicil, kaynak)"),
    ("ubo_reverified", "Gerçek faydalanıcı yapısı yeniden doğrulandı"),
    ("purpose_nature", "İş ilişkisinin amacı ve niteliği yeniden değerlendirildi"),
    ("source_of_funds", "Fon ve servet kaynağına ilişkin bilgi ve belge alındı"),
    ("senior_approval", "İlişkinin sürdürülmesi için üst yönetim onayı alındı"),
    ("monitoring_plan", "Artırılmış izleme sıklığı ve kapsamı kararlaştırıldı"),
    ("suspicion_review", "Şüphe değerlendirmesi yapıldı (sonuç yetkili kayıtta tutulur)"),
)
"""Genel bir **şablondur**, mevzuat yorumu değildir. FATF Tavsiye 10/12'deki sıkılaştırılmış
tedbir başlıklarından derlenmiştir; kurum kendi politikasına göre uyarlar."""


def new_checklist() -> list[dict[str, Any]]:
    return [{"key": k, "label": label, "done": False, "note": None} for k, label in EDD_TEMPLATE]


def checklist_complete(items: Iterable[Mapping[str, Any]] | None) -> bool:
    rows = list(items or ())
    return bool(rows) and all(bool(r.get("done")) for r in rows)


# --- Süre (SLA) -----------------------------------------------------------------------------

DEFAULT_SLA_DAYS: dict[str, int] = {"critical": 2, "high": 5, "info": 10}
"""Ürün varsayılanı (gün). Mevzuat süresi değildir; kurum kendi iç süresini seçer."""


def due_at_for(severity: str, opened_at: datetime) -> datetime:
    return opened_at + timedelta(days=DEFAULT_SLA_DAYS.get(severity, DEFAULT_SLA_DAYS["info"]))


def is_overdue(status: str, due_at: datetime | None, now: datetime) -> bool:
    return due_at is not None and CaseStatus(status) in OPEN_STATUSES and now > due_at
