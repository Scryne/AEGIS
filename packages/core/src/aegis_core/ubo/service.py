"""UBO hesabının veritabanı tarafı (E2.1).

1. Hedef şirketten **yukarı** doğru sahiplik ve kontrol zincirini özyinelemeli bir CTE ile
   toplar (ROADMAP: *"Postgres recursive CTE from target company through ownership
   chains"*). CTE ziyaret edilen düğümleri yol dizisinde taşır ve bir düğüme ikinci kez
   girmez; döngülü yapı sonsuz özyinelemeye düşmez. Döngünün kendisi saf çekirdekte açıkça
   raporlanır.
2. Toplanan düğüm ve kenarları ``compute.compute_ubo``'ya verir (saf, deterministik).
3. Sonucu, girdilerin donmuş kopyası ve özetiyle ``ubo_computation`` satırı olarak yazar ve
   tek bir denetim olayı üretir (Invariant 2: risk-etkileyen her eylem bir olay).

Yalnız geçerli bağlar sayılır: ``end_date`` geçmişte kalmış ortaklık hesaba girmez.
Birleştirilmiş (``merged``) varlıkların bağları da girmez — onların bağları ER sırasında
hayatta kalan kayda taşınır.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aegis_core.models import AuditAction, Entity, EntityStatus, RelationshipType
from aegis_core.models.screening import Screening
from aegis_core.models.ubo import UboComputation
from aegis_core.services import audit as audit_service
from aegis_core.ubo.compute import DEFAULT_THRESHOLD, Edge, EdgeKind, Node, UboResult, compute_ubo

# rel_type → hesaptaki anlamı. ``ubo`` (beyan edilmiş UBO) burada bir *girdi* değildir:
# hesap, beyanı değil sahiplik zincirini çözer; beyanla hesap farklıysa ikisi yan yana görünür.
_KIND = {
    RelationshipType.SHAREHOLDER.value: EdgeKind.OWNERSHIP,
    RelationshipType.CONTROL.value: EdgeKind.CONTROL,
    RelationshipType.OFFICER.value: EdgeKind.OFFICER,
}

_CHAIN_SQL = text(
    """
    WITH RECURSIVE chain(entity_id, path) AS (
        SELECT CAST(:target AS uuid), ARRAY[CAST(:target AS uuid)]
      UNION
        SELECT r.source_entity_id, c.path || r.source_entity_id
        FROM relationship r
        JOIN chain c ON r.target_entity_id = c.entity_id
        WHERE r.rel_type = 'shareholder'
          AND (r.end_date IS NULL OR r.end_date >= :today)
          AND NOT r.source_entity_id = ANY(c.path)
    )
    SELECT DISTINCT entity_id FROM chain
    """
)


async def load_graph(
    session: AsyncSession, target_id: uuid.UUID, *, today: date | None = None
) -> tuple[dict[str, Node], list[Edge]]:
    today = today or datetime.now(UTC).date()
    rows = await session.execute(_CHAIN_SQL, {"target": target_id, "today": today})
    chain_ids = {row[0] for row in rows}

    # Zincirdeki şirketlere işaret eden bütün geçerli bağlar (döngüyü kapatan kenar dahil):
    # sahiplik + kontrol (zincirdeki her şirket) + yönetici (yalnız hedef).
    edge_rows = await session.execute(
        text(
            """
            SELECT r.id, r.source_entity_id, r.target_entity_id, r.rel_type, r.ownership_percent
            FROM relationship r
            WHERE r.target_entity_id = ANY(:ids)
              AND r.rel_type IN ('shareholder', 'control', 'officer')
              AND (r.end_date IS NULL OR r.end_date >= :today)
            ORDER BY r.created_at, r.id
            """
        ),
        {"ids": list(chain_ids), "today": today},
    )
    edges: list[Edge] = []
    node_ids: set[uuid.UUID] = set(chain_ids)
    for rel_id, source, target, rel_type, percent in edge_rows:
        if rel_type == RelationshipType.OFFICER.value and target != target_id:
            continue
        edges.append(
            Edge(
                owner=str(source),
                owned=str(target),
                kind=_KIND[rel_type],
                percent=Decimal(percent) if percent is not None else None,
                relationship_id=str(rel_id),
            )
        )
        node_ids.add(source)

    entities = await session.scalars(select(Entity).where(Entity.id.in_(node_ids)))
    nodes = {
        str(e.id): Node(str(e.id), e.schema_type, e.name, e.country)
        for e in entities
        if e.status == EntityStatus.ACTIVE.value
    }
    # Birleştirilmiş/erişilemeyen uçlara giden kenarlar düşer; hedef her zaman kalır.
    edges = [e for e in edges if e.owner in nodes and e.owned in nodes]
    return nodes, edges


def canonical_inputs(target: str, nodes: dict[str, Node], edges: list[Edge]) -> dict[str, Any]:
    return {
        "target": target,
        "nodes": [
            {"id": n.id, "schema": n.schema, "name": n.name, "country": n.country}
            for n in sorted(nodes.values(), key=lambda n: n.id)
        ],
        "edges": [
            {
                "owner": e.owner,
                "owned": e.owned,
                "kind": e.kind.value,
                "percent": str(e.percent) if e.percent is not None else None,
                "relationship_id": e.relationship_id,
            }
            for e in sorted(
                edges, key=lambda e: (e.owned, e.owner, e.kind.value, e.relationship_id or "")
            )
        ],
    }


def input_digest(inputs: dict[str, Any]) -> str:
    blob = json.dumps(inputs, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def compute_and_store(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity: Entity,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    threshold: Decimal = DEFAULT_THRESHOLD,
    inclusive: bool = False,
    retention_years: int = 5,
) -> tuple[UboComputation, UboResult]:
    nodes, edges = await load_graph(session, entity.id)
    result = compute_ubo(str(entity.id), nodes, edges, threshold=threshold, inclusive=inclusive)
    inputs = canonical_inputs(str(entity.id), nodes, edges)
    row = UboComputation(
        tenant_id=tenant_id,
        entity_id=entity.id,
        status=result.status.value,
        threshold_percent=threshold,
        threshold_inclusive=inclusive,
        result=result.to_dict(),
        inputs=inputs,
        input_sha256=input_digest(inputs),
        computed_by_user_id=actor_user_id,
        retention_until=datetime.now(UTC) + timedelta(days=365 * retention_years),
    )
    session.add(row)
    await session.flush()
    await audit_service.record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=AuditAction.UBO_COMPUTE,
        object_type="ubo_computation",
        object_id=str(row.id),
        payload={
            "entity_id": str(entity.id),
            "status": result.status.value,
            "threshold": str(threshold),
            "inclusive": inclusive,
            "ubo_ids": [u.entity_id for u in result.ubos],
            "input_sha256": row.input_sha256,
        },
    )
    return row, result


async def latest(session: AsyncSession, entity_id: uuid.UUID) -> UboComputation | None:
    row: UboComputation | None = await session.scalar(
        select(UboComputation)
        .where(UboComputation.entity_id == entity_id)
        .order_by(UboComputation.created_at.desc(), UboComputation.id.desc())
        .limit(1)
    )
    return row


async def history(
    session: AsyncSession, entity_id: uuid.UUID, limit: int = 20
) -> list[UboComputation]:
    rows = await session.scalars(
        select(UboComputation)
        .where(UboComputation.entity_id == entity_id)
        .order_by(UboComputation.created_at.desc(), UboComputation.id.desc())
        .limit(limit)
    )
    return list(rows)


async def unscreened(session: AsyncSession, entity_ids: list[str]) -> list[str]:
    """Hiç taranmamış UBO'lar — E2.1: "auto-trigger screening for newly identified UBOs"."""
    if not entity_ids:
        return []
    ids = [uuid.UUID(i) for i in entity_ids]
    screened = set(
        await session.scalars(select(Screening.entity_id).where(Screening.entity_id.in_(ids)))
    )
    return [i for i in entity_ids if uuid.UUID(i) not in screened]
