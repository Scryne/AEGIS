"""Alarm önem derecesi (E3.1) — saf çekirdek, veritabanı ve ağ bilmez.

ROADMAP E3.1: *"Alert severity model (critical: new sanctions hit / high: ownership change /
info)"*. Mülkiyet değişikliği algılaması (sicil/gazete farkı) henüz yok; o kaynak geldiğinde
``high`` kademesine eklenir. Bugünkü kurallar fark kalemlerinin kendisinden çıkar:

* **critical** — bir kayda yaptırım etiketi geldi: yaptırım konulu yeni aday ya da mevcut
  kayda ``sanction*`` etiketinin eklenmesi.
* **high** — PEP etiketi geldi (yeni aday ya da eklenen etiket) veya onaylanmış bir eşleşme
  listeden çıktı (onaylı yaptırımın kaybolması da incelenir).
* **info** — geri kalan önemli farklar: konusuz yeni aday, etiket düşmesi.

Alarmın derecesi kalemlerinin en yükseğidir. "Yaptırım" ve "PEP"in ne olduğu
``screening/topics.py``'dedir; burada tekrar tanımlanmaz.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any

from aegis_core.screening.topics import has_pep_topic, has_sanction_topic


class Severity(StrEnum):
    INFO = "info"
    HIGH = "high"
    CRITICAL = "critical"


RANK: dict[Severity, int] = {Severity.INFO: 0, Severity.HIGH: 1, Severity.CRITICAL: 2}

SEVERITY_LABELS: dict[Severity, str] = {
    Severity.CRITICAL: "Kritik",
    Severity.HIGH: "Yüksek",
    Severity.INFO: "Bilgi",
}


def item_severity(item: Mapping[str, Any]) -> Severity:
    """Tek bir fark kalemi (``DiffItem.to_dict`` biçimi) için derece."""
    kind = item.get("kind")
    added = tuple(item.get("topics_added") or ())
    if kind in ("new_match", "topics_changed") and has_sanction_topic(added):
        return Severity.CRITICAL
    if kind == "removed_confirmed":
        return Severity.HIGH
    if kind in ("new_match", "topics_changed") and has_pep_topic(added):
        return Severity.HIGH
    return Severity.INFO


def alert_severity(items: Iterable[Mapping[str, Any]]) -> Severity:
    """Alarmın derecesi: kalemlerin en yükseği; kalem yoksa ``info``."""
    best = Severity.INFO
    for item in items:
        sev = item_severity(item)
        if RANK[sev] > RANK[best]:
            best = sev
    return best
