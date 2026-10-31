"""UBO saf çekirdeği (E2.1): katmanlı yapı, çapraz ortaklık, döngü, %25 sınırı, çözülemeyenler."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aegis_core.ubo.compute import Basis, Edge, EdgeKind, Node, UboStatus, compute_ubo

D = Decimal


def person(pid: str) -> Node:
    return Node(pid, "Person", pid.capitalize())


def company(cid: str, country: str | None = "TR") -> Node:
    return Node(cid, "Company", cid.upper(), country)


def own(owner: str, owned: str, pct: str | None) -> Edge:
    return Edge(owner, owned, EdgeKind.OWNERSHIP, D(pct) if pct is not None else None)


def nodes(*items: Node) -> dict[str, Node]:
    return {n.id: n for n in items}


def shares(result) -> dict[str, Decimal]:
    return {u.entity_id: u.effective_percent for u in result.ubos}


def test_direct_owners_above_threshold():
    g = nodes(company("t"), person("ali"), person("ayse"), person("can"))
    r = compute_ubo("t", g, [own("ali", "t", "60"), own("ayse", "t", "30"), own("can", "t", "10")])
    assert r.status is UboStatus.DETERMINED
    assert shares(r) == {"ali": D(60), "ayse": D(30)}
    assert r.unattributed_percent == 0
    assert r.cycles == []
    assert r.unresolved == []


def test_layered_structure_multiplies_shares():
    # ali %80 → H1 %50 → T  ⇒ ali %40; veli %20 → H1 ⇒ %10 (eşik altı)
    g = nodes(
        company("t"), company("h1"), company("h2"), person("ali"), person("veli"), person("zeynep")
    )
    r = compute_ubo(
        "t",
        g,
        [
            own("h1", "t", "50"),
            own("h2", "t", "50"),
            own("ali", "h1", "80"),
            own("veli", "h1", "20"),
            own("zeynep", "h2", "100"),
        ],
    )
    assert r.status is UboStatus.DETERMINED
    assert shares(r) == {"zeynep": D(50), "ali": D(40)}
    ali = next(u for u in r.ubos if u.entity_id == "ali")
    assert ali.paths == [["ali", "h1", "t"]]


def test_indirect_paths_are_summed():
    # ali doğrudan %15 + H üzerinden %50·%30 = %15 ⇒ toplam %30 (tek yol eşik altı, toplam üstü)
    g = nodes(company("t"), company("h"), person("ali"), person("b"), person("c"))
    edges = [own("ali", "t", "15"), own("h", "t", "50"), own("b", "t", "35")]
    r = compute_ubo("t", g, [*edges, own("ali", "h", "30"), own("c", "h", "70")])
    assert r.status is UboStatus.DETERMINED
    assert shares(r)["ali"] == D(30)
    assert sorted(len(p) for p in next(u for u in r.ubos if u.entity_id == "ali").paths) == [2, 3]


@pytest.mark.parametrize(
    ("inclusive", "expected"), [(False, set()), (True, {"ali", "b", "c", "d"})]
)
def test_exact_25_percent_boundary(inclusive, expected):
    g = nodes(company("t"), *(person(p) for p in ("ali", "b", "c", "d")))
    r = compute_ubo(
        "t", g, [own(p, "t", "25") for p in ("ali", "b", "c", "d")], inclusive=inclusive
    )
    assert set(shares(r)) == expected
    assert r.inclusive is inclusive


def test_layered_boundary_is_exact_decimal():
    # %50 · %50 = tam %25: ondalık aritmetik, kayan nokta kayması yok.
    g = nodes(company("t"), company("h"), person("ali"), person("b"), person("c"))
    r = compute_ubo(
        "t",
        g,
        [own("h", "t", "50"), own("b", "t", "50"), own("ali", "h", "50"), own("c", "h", "50")],
        inclusive=True,
    )
    assert shares(r)["ali"] == D(25)


def test_circular_ownership_is_surfaced_not_absorbed():
    # T ← A %60, A ← B %100, B ← A %40 (çapraz), A ← ali %60
    g = nodes(company("t"), company("a"), company("b"), person("ali"), person("x"))
    edges = [
        own("a", "t", "60"),
        own("x", "t", "40"),
        own("b", "a", "40"),
        own("ali", "a", "60"),
        own("a", "b", "100"),
    ]
    r = compute_ubo("t", g, edges)
    assert r.cycles
    assert set(r.cycles[0]) == {"a", "b"}
    # A'nın %40'ı döngüde kalır: 0.6·0.4 = %24 hiçbir kişiye bağlanmaz (eşik altı).
    assert r.unattributed_percent == D(24)
    assert shares(r) == {"ali": D(36), "x": D(40)}
    assert r.status is UboStatus.DETERMINED


def test_cycle_holding_most_shares_makes_result_not_determinable():
    g = nodes(company("t"), company("a"), company("b"), person("ali"))
    r = compute_ubo(
        "t",
        g,
        [own("a", "t", "100"), own("b", "a", "90"), own("ali", "a", "10"), own("a", "b", "100")],
    )
    assert r.status is UboStatus.NOT_DETERMINABLE
    assert r.cycles


def test_foreign_parent_without_owners_is_reported():
    g = nodes(company("t"), company("holding", country="NL"), person("ali"))
    r = compute_ubo("t", g, [own("holding", "t", "70"), own("ali", "t", "30")])
    assert r.status is UboStatus.NOT_DETERMINABLE
    assert shares(r) == {"ali": D(30)}
    (u,) = r.unresolved
    assert u.entity_id == "holding"
    assert "yabancı" in u.reason
    assert u.share_percent == D(70)


def test_missing_percentage_blocks_determination():
    g = nodes(company("t"), person("ali"), person("b"))
    r = compute_ubo("t", g, [own("ali", "t", "60"), own("b", "t", None)])
    assert r.status is UboStatus.NOT_DETERMINABLE
    assert shares(r) == {"ali": D(60)}
    assert "pay girilmemiş" in r.unresolved[0].reason
    assert r.unresolved[0].share_percent is None


def test_shares_not_adding_to_100_leave_a_gap():
    g = nodes(company("t"), person("ali"))
    r = compute_ubo("t", g, [own("ali", "t", "40")])
    assert r.status is UboStatus.NOT_DETERMINABLE
    assert r.unattributed_percent == D(60)


def test_control_then_senior_management_fallback():
    g = nodes(company("t"), *(person(p) for p in ("a", "b", "c", "d", "e", "mudur", "kontrol")))
    dispersed = [own(p, "t", "20") for p in ("a", "b", "c", "d", "e")]
    with_control = [*dispersed, Edge("kontrol", "t", EdgeKind.CONTROL)]
    r = compute_ubo("t", g, with_control)
    assert [(u.entity_id, u.basis) for u in r.ubos] == [("kontrol", Basis.CONTROL)]

    officers = [*dispersed, Edge("mudur", "t", EdgeKind.OFFICER)]
    r = compute_ubo("t", g, officers)
    assert [(u.entity_id, u.basis) for u in r.ubos] == [("mudur", Basis.SENIOR_MANAGEMENT)]
    assert r.status is UboStatus.DETERMINED


def test_nobody_at_all():
    g = nodes(company("t"), *(person(p) for p in ("a", "b", "c", "d", "e")))
    r = compute_ubo("t", g, [own(p, "t", "20") for p in ("a", "b", "c", "d", "e")])
    assert r.status is UboStatus.NONE_FOUND
    assert r.ubos == []


def test_result_is_serializable_and_deterministic():
    g = nodes(company("t"), person("ali"))
    first = compute_ubo("t", g, [own("ali", "t", "100")]).to_dict()
    assert first == compute_ubo("t", g, [own("ali", "t", "100")]).to_dict()
    assert first["ubos"][0]["effective_percent"] == "100"
    assert first["threshold"] == "25"
