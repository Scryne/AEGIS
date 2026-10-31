"""İzleme-lite (E2.4) — iki tarama koşusu arasındaki yapısal fark, saf çekirdek.

ROADMAP: *"re-screen watched entities → structural diff vs. last confirmed results
(new/changed/removed matches)"*. Aday kimliği ``(subject_key, external_id)`` çiftidir: aynı
özne için aynı liste kaydı. Karşılaştırma, insanın önceki kararlarını hesaba katar:

* **Yeni eşleşme** — önceki koşuda olmayan ve motorun otomatik elemediği aday. Önceden
  insanın elediği bir aday yeniden gelirse "yeni" değildir (zaten karara bağlandı); bu,
  bilinen yanlış pozitiflerin her gece alarm üretmesini önler.
* **Listeden çıkan** — önceki koşuda **onaylanmış** bir eşleşme artık gelmiyor (liste
  kaydı kaldırıldı ya da değişti). Onaylı bir yaptırımın kaybolması da incelenmelidir.
* **Değişen** — aynı kayıt, farklı konu etiketleriyle (ör. ``role.pep`` → ``sanction``).
  İnsanın elediği bir kayıtta yalnız *eklenen* etiket önemlidir.

Bu modül veritabanı ve ağ bilmez; aynı girdi aynı farkı verir.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CandidateView:
    subject_key: str
    subject_name: str
    external_id: str
    caption: str
    score: float
    topics: tuple[str, ...]
    decision: str  # pending | confirmed | dismissed
    decided_automatically: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject_key, self.external_id)

    @property
    def auto_dismissed(self) -> bool:
        return self.decision == "dismissed" and self.decided_automatically


@dataclass(frozen=True)
class DiffItem:
    kind: str  # new_match | removed_confirmed | topics_changed
    subject_name: str
    external_id: str
    caption: str
    detail: str
    topics_added: tuple[str, ...] = ()
    topics_removed: tuple[str, ...] = ()


@dataclass
class ScreeningDiff:
    items: list[DiffItem] = field(default_factory=list)

    @property
    def material(self) -> bool:
        return bool(self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "kind": i.kind,
                    "subject_name": i.subject_name,
                    "external_id": i.external_id,
                    "caption": i.caption,
                    "detail": i.detail,
                    "topics_added": list(i.topics_added),
                    "topics_removed": list(i.topics_removed),
                }
                for i in self.items
            ]
        }


def diff_candidates(
    previous: Sequence[CandidateView], current: Sequence[CandidateView]
) -> ScreeningDiff:
    prev = {c.key: c for c in previous}
    curr = {c.key: c for c in current}
    out = ScreeningDiff()

    for key, cand in sorted(curr.items()):
        if cand.auto_dismissed:
            continue
        old = prev.get(key)
        if old is None:
            out.items.append(
                DiffItem(
                    "new_match",
                    cand.subject_name,
                    cand.external_id,
                    cand.caption,
                    f"Yeni aday (skor {cand.score:.2f}"
                    + (f"; konular: {', '.join(cand.topics)}" if cand.topics else "")
                    + ")",
                    topics_added=cand.topics,
                )
            )
            continue
        added = tuple(sorted(set(cand.topics) - set(old.topics)))
        removed = tuple(sorted(set(old.topics) - set(cand.topics)))
        if not added and not removed:
            continue
        if old.decision == "dismissed" and not added:
            continue  # elenmiş kayıttan etiket düşmesi bir risk değişimi değildir
        out.items.append(
            DiffItem(
                "topics_changed",
                cand.subject_name,
                cand.external_id,
                cand.caption,
                "Liste kaydının konu etiketleri değişti"
                + (f"; eklendi: {', '.join(added)}" if added else "")
                + (f"; çıkarıldı: {', '.join(removed)}" if removed else ""),
                topics_added=added,
                topics_removed=removed,
            )
        )

    for key, old in sorted(prev.items()):
        if key in curr or old.decision != "confirmed":
            continue
        out.items.append(
            DiffItem(
                "removed_confirmed",
                old.subject_name,
                old.external_id,
                old.caption,
                "Onaylanmış eşleşme bu koşuda gelmedi "
                "(liste kaydı kaldırılmış ya da değişmiş olabilir).",
            )
        )
    return out
