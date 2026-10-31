"""Gerçek faydalanıcı (UBO) hesabı — saf çekirdek (E2.1).

Girdi: hedef şirketten yukarı doğru toplanmış sahiplik/kontrol kenarları ve düğüm
bilgisi (veritabanı katmanı ``ubo.service`` toplar). Çıktı: kimlerin hangi yollardan,
hangi etkin payla gerçek faydalanıcı sayıldığı; döngüler; ve **neden** belirlenemediği.

Kurallar:

* **Etkin pay** = bir kişiden hedefe giden her sahiplik yolunda payların çarpımı; aynı
  kişinin birden çok yolu toplanır (dolaylı + doğrudan, çapraz ortaklık).
* **Eşik** varsayılan olarak "%25'ten fazla"dır (``inclusive=False``); MASAK düzenlemesinin
  ifadesi "yüzde yirmi beşinden fazla"dır. Kapsayıcı (≥) yorum için ``inclusive=True``. Eşik
  ve yorum her sonuçla birlikte saklanır; denetçi hangi kuralla hesaplandığını görür.
* **Döngü** (A, B'nin; B, A'nın ortağı) sessizce yutulmaz: yol döngüye girdiği noktada
  kesilir ve döngü açıkça listelenir. Döngüdeki pay o yoldan hiçbir kişiye aktarılmaz;
  bu yüzden sonuç ``not_determinable`` olabilir — bu da kendi başına bir MASAK sinyalidir.
* **Çözülemeyen zincir**: ortakları kayıtlı olmayan bir tüzel kişi (yabancı ana şirket,
  eksik veri) ya da payı girilmemiş bir sahiplik bağı. Bu durumlarda "UBO yok" denmez;
  hangi şirkette, hangi nedenle ve ne kadarlık payın belirsiz kaldığı raporlanır.
* Pay eşiği aşan kimse yoksa sıradaki dayanaklar: hedef ya da zincirdeki bir şirket
  üzerinde **kontrol** bağı olan kişiler, o da yoksa hedefin **üst düzey yöneticileri**
  (``officer``). Hangi dayanağın kullanıldığı ``basis`` alanında yazılır.

Bu modül veritabanına, saate ve ağa dokunmaz; aynı girdi her zaman aynı çıktıyı verir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

HUNDRED = Decimal(100)
DEFAULT_THRESHOLD = Decimal(25)


class EdgeKind(StrEnum):
    OWNERSHIP = "ownership"
    CONTROL = "control"
    OFFICER = "officer"


class Basis(StrEnum):
    OWNERSHIP = "ownership"
    CONTROL = "control"
    SENIOR_MANAGEMENT = "senior_management"


class UboStatus(StrEnum):
    DETERMINED = "determined"
    """En az bir gerçek faydalanıcı bulundu ve belirsiz kalan pay eşiği aşamaz."""

    NOT_DETERMINABLE = "not_determinable"
    """Belirsiz kalan pay (çözülemeyen zincir ya da döngü) eşiği aşabilecek kadar büyük:
    sonuç verilemez, nedenleri ``unresolved``/``cycles`` alanındadır."""

    NONE_FOUND = "none_found"
    """Zincir tam çözüldü ama eşiği aşan, kontrol eden ya da yönetici kişi yok."""


@dataclass(frozen=True)
class Node:
    id: str
    schema: str  # "Person" | "Company"
    name: str
    country: str | None = None


@dataclass(frozen=True)
class Edge:
    owner: str
    owned: str
    kind: EdgeKind
    percent: Decimal | None = None
    relationship_id: str | None = None


@dataclass
class UboPerson:
    entity_id: str
    name: str
    basis: Basis
    effective_percent: Decimal
    paths: list[list[str]] = field(default_factory=list)


@dataclass
class Unresolved:
    entity_id: str
    name: str
    reason: str
    share_percent: Decimal | None
    """Bu düğümden hedefe akan etkin pay (biliniyorsa)."""


@dataclass
class UboResult:
    status: UboStatus
    threshold: Decimal
    inclusive: bool
    ubos: list[UboPerson]
    unresolved: list[Unresolved]
    cycles: list[list[str]]
    unattributed_percent: Decimal
    """Hiçbir kişiye bağlanamayan toplam etkin pay (çözülemeyen + döngüde kalan)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "threshold": str(self.threshold),
            "inclusive": self.inclusive,
            "ubos": [
                {
                    "entity_id": u.entity_id,
                    "name": u.name,
                    "basis": u.basis.value,
                    "effective_percent": _fmt(u.effective_percent),
                    "paths": u.paths,
                }
                for u in self.ubos
            ],
            "unresolved": [
                {
                    "entity_id": u.entity_id,
                    "name": u.name,
                    "reason": u.reason,
                    "share_percent": _fmt(u.share_percent) if u.share_percent is not None else None,
                }
                for u in self.unresolved
            ],
            "cycles": self.cycles,
            "unattributed_percent": _fmt(self.unattributed_percent),
        }


def _fmt(value: Decimal) -> str:
    # normalize() 100'ü "1E+2" yazar; sabit noktalı yazıp sondaki sıfırları kırpıyoruz.
    text = format(value.quantize(Decimal("0.0001")), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _passes(value: Decimal, threshold: Decimal, inclusive: bool) -> bool:
    return value >= threshold if inclusive else value > threshold


def compute_ubo(
    target: str,
    nodes: dict[str, Node],
    edges: list[Edge],
    *,
    threshold: Decimal = DEFAULT_THRESHOLD,
    inclusive: bool = False,
) -> UboResult:
    if target not in nodes:
        raise ValueError(f"hedef düğüm yok: {target}")

    owners_of: dict[str, list[Edge]] = defaultdict(list)
    controllers_of: dict[str, list[Edge]] = defaultdict(list)
    officers_of: dict[str, list[Edge]] = defaultdict(list)
    for edge in edges:
        if edge.kind is EdgeKind.OWNERSHIP:
            owners_of[edge.owned].append(edge)
        elif edge.kind is EdgeKind.CONTROL:
            controllers_of[edge.owned].append(edge)
        else:
            officers_of[edge.owned].append(edge)

    person_share: dict[str, Decimal] = defaultdict(Decimal)
    person_paths: dict[str, list[list[str]]] = defaultdict(list)
    unresolved: dict[tuple[str, str], Decimal | None] = {}
    cycles: list[list[str]] = []
    seen_cycles: set[frozenset[str]] = set()
    unattributed = Decimal(0)
    chain_companies: set[str] = {target}

    def mark_unresolved(node_id: str, reason: str, share: Decimal | None) -> None:
        key = (node_id, reason)
        if share is None or unresolved.get(key, Decimal(0)) is None:
            unresolved[key] = None
        else:
            unresolved[key] = (unresolved.get(key) or Decimal(0)) + share

    def walk(node_id: str, share: Decimal, path: list[str]) -> None:
        """``share``: bu düğümün hedefteki etkin payı (oran, 0–1)."""
        nonlocal unattributed
        node = nodes.get(node_id)
        if node is None:
            mark_unresolved(node_id, "kayıtlı olmayan varlık", share * HUNDRED)
            unattributed += share
            return
        if node.schema == "Person":
            person_share[node_id] += share
            person_paths[node_id].append(list(reversed(path)))
            return
        chain_companies.add(node_id)
        owners = owners_of.get(node_id, [])
        if not owners:
            if node_id != target:
                reason = (
                    "yabancı tüzel kişi; ortakları kayıtlı değil"
                    if node.country and node.country.upper() not in ("TR", "TUR")
                    else "ortakları kayıtlı değil"
                )
                mark_unresolved(node_id, reason, share * HUNDRED)
                unattributed += share
            return
        known = Decimal(0)
        for edge in owners:
            if edge.owner in path:
                cycle = [*path[path.index(edge.owner) :], edge.owner]
                key = frozenset(cycle)
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(list(reversed(cycle)))
                # Döngüye giren pay kimseye aktarılmaz ama "kayıtlı pay" sayılır; aksi halde
                # aşağıdaki "%100'e ulaşmıyor" kontrolü aynı payı ikinci kez belirsiz sayardı.
                known += edge.percent or Decimal(0)
                unattributed += (edge.percent or Decimal(0)) / HUNDRED * share
                continue
            if edge.percent is None:
                owner_name = nodes[edge.owner].name if edge.owner in nodes else edge.owner
                mark_unresolved(node_id, f"pay girilmemiş: {owner_name}", None)
                continue
            fraction = edge.percent / HUNDRED
            known += edge.percent
            walk(edge.owner, share * fraction, [*path, edge.owner])
        if known < HUNDRED and not any(e.percent is None for e in owners):
            # Kayıtlı payların toplamı %100'e ulaşmıyor: kalan pay kimsede değil.
            missing = (HUNDRED - known) / HUNDRED * share
            mark_unresolved(node_id, "kayıtlı paylar %100'e ulaşmıyor", missing * HUNDRED)
            unattributed += missing

    walk(target, Decimal(1), [target])

    threshold_fraction = threshold / HUNDRED
    ubos = [
        UboPerson(
            entity_id=pid,
            name=nodes[pid].name,
            basis=Basis.OWNERSHIP,
            effective_percent=share * HUNDRED,
            paths=person_paths[pid],
        )
        for pid, share in person_share.items()
        if _passes(share, threshold_fraction, inclusive)
    ]
    ubos.sort(key=lambda u: (-u.effective_percent, u.name))

    # Belirsiz pay eşiği aşabiliyorsa ya da bir payın büyüklüğü hiç bilinmiyorsa, bulunanlar
    # tam liste olmayabilir: sonuç "belirlenemedi"dir (bulunanlar yine listelenir).
    missing_share_percent = any(v is None for v in unresolved.values())
    undeterminable = _passes(unattributed, threshold_fraction, inclusive) or missing_share_percent

    if not ubos and not undeterminable:
        controllers: dict[str, list[list[str]]] = defaultdict(list)
        for company in sorted(chain_companies):
            for edge in controllers_of.get(company, []):
                if nodes.get(edge.owner) and nodes[edge.owner].schema == "Person":
                    controllers[edge.owner].append([edge.owner, company])
        if controllers:
            ubos = [
                UboPerson(
                    pid,
                    nodes[pid].name,
                    Basis.CONTROL,
                    person_share.get(pid, Decimal(0)) * HUNDRED,
                    paths,
                )
                for pid, paths in controllers.items()
            ]
        else:
            officers = [
                e.owner
                for e in officers_of.get(target, [])
                if nodes.get(e.owner) and nodes[e.owner].schema == "Person"
            ]
            ubos = [
                UboPerson(
                    pid,
                    nodes[pid].name,
                    Basis.SENIOR_MANAGEMENT,
                    person_share.get(pid, Decimal(0)) * HUNDRED,
                    [[pid, target]],
                )
                for pid in dict.fromkeys(officers)
            ]
        ubos.sort(key=lambda u: u.name)

    if undeterminable:
        status = UboStatus.NOT_DETERMINABLE
    elif ubos:
        status = UboStatus.DETERMINED
    else:
        status = UboStatus.NONE_FOUND

    return UboResult(
        status=status,
        threshold=threshold,
        inclusive=inclusive,
        ubos=ubos,
        unresolved=[
            Unresolved(nid, nodes[nid].name if nid in nodes else nid, reason, share)
            for (nid, reason), share in unresolved.items()
        ],
        cycles=cycles,
        unattributed_percent=unattributed * HUNDRED,
    )
