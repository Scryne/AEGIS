// Gerçek faydalanıcı (E2.1) — API yanıt tipleri ve grafın katman yerleşimi.

export interface UboPerson {
  entity_id: string;
  name: string;
  basis: "ownership" | "control" | "senior_management";
  effective_percent: string;
  paths: string[][];
}

export interface UboUnresolved {
  entity_id: string;
  name: string;
  reason: string;
  share_percent: string | null;
}

export interface UboNode {
  id: string;
  schema: "Person" | "Company";
  name: string;
  country: string | null;
}

export interface UboEdge {
  owner: string;
  owned: string;
  kind: "ownership" | "control" | "officer";
  percent: string | null;
  relationship_id: string | null;
}

export interface UboComputation {
  id: string;
  entity_id: string;
  status: "determined" | "not_determinable" | "none_found";
  threshold_percent: string;
  inclusive: boolean;
  ubos: UboPerson[];
  unresolved: UboUnresolved[];
  cycles: string[][];
  unattributed_percent: string;
  nodes: UboNode[];
  edges: UboEdge[];
  input_sha256: string;
  created_at: string;
  unscreened_ubo_ids: string[];
}

export const STATUS_LABELS: Record<UboComputation["status"], string> = {
  determined: "Belirlendi",
  not_determinable: "Belirlenemedi",
  none_found: "Eşiği aşan kişi yok",
};

export const BASIS_LABELS: Record<UboPerson["basis"], string> = {
  ownership: "Pay sahipliği",
  control: "Kontrol",
  senior_management: "Üst düzey yönetici",
};

export interface PlacedNode extends UboNode {
  x: number;
  y: number;
  layer: number;
}

export const NODE_W = 200;
export const NODE_H = 52;
const GAP_X = 28;
const GAP_Y = 64;
/** Katman atlayan okun ara katmanda kapladığı dar yuva (görünmez yol noktası). */
const WAYPOINT_W = 56;

export function edgeKey(edge: UboEdge): string {
  return `${edge.owner}>${edge.owned}>${edge.relationship_id ?? edge.kind}`;
}

/**
 * Katmanlı yerleşim: hedef en altta (katman 0), sahipler yukarıda. Bir düğümün katmanı,
 * hedefe giden en uzun döngüsüz yolun uzunluğudur; böylece her ok yukarıdan aşağı akar.
 * Döngüdeki kenarlar katman hesabında yok sayılır (onlar ayrıca kesikli çizilir).
 *
 * Birden çok katman atlayan ok (ör. holdinge de ortak olan kişinin hedefteki doğrudan payı)
 * ara katmanlarda kendine ait dar bir yuva alır ve oradan geçen kırık çizgiyle çizilir;
 * yoksa ara katmandaki düğümlerin altından geçer ve etiketi görünmez olurdu.
 */
export function layout(target: string, nodes: UboNode[], edges: UboEdge[]) {
  const ownersOf = new Map<string, string[]>();
  for (const edge of edges) {
    const list = ownersOf.get(edge.owned) ?? [];
    list.push(edge.owner);
    ownersOf.set(edge.owned, list);
  }
  const layer = new Map<string, number>([[target, 0]]);
  const visit = (id: string, depth: number, path: Set<string>) => {
    for (const owner of ownersOf.get(id) ?? []) {
      if (path.has(owner)) continue;
      if ((layer.get(owner) ?? -1) < depth + 1) layer.set(owner, depth + 1);
      path.add(owner);
      visit(owner, depth + 1, path);
      path.delete(owner);
    }
  };
  visit(target, 0, new Set([target]));
  for (const node of nodes) if (!layer.has(node.id)) layer.set(node.id, 1);

  type Slot = { id: string; sortKey: string; w: number; node?: UboNode };
  const names = new Map(nodes.map((n) => [n.id, n.name]));
  const rows = new Map<number, Slot[]>();
  const add = (l: number, slot: Slot) => rows.set(l, [...(rows.get(l) ?? []), slot]);
  for (const node of nodes) add(layer.get(node.id) ?? 0, { id: node.id, sortKey: node.name, w: NODE_W, node });
  const waypointIds = new Map<string, string[]>();
  for (const edge of edges) {
    const top = layer.get(edge.owner) ?? 0;
    const bottom = layer.get(edge.owned) ?? 0;
    if (top - bottom < 2) continue;
    const ids: string[] = [];
    for (let l = top - 1; l > bottom; l--) {
      const id = `${edgeKey(edge)}@${l}`;
      // Kaynağının adıyla sıralanır: yuva sahibinin hizasına yakın düşer.
      add(l, { id, sortKey: `${names.get(edge.owner) ?? ""}\u0000`, w: WAYPOINT_W });
      ids.push(id);
    }
    waypointIds.set(edgeKey(edge), ids);
  }

  const maxLayer = Math.max(0, ...layer.values());
  const rowWidth = (row: Slot[]) => row.reduce((sum, s) => sum + s.w, 0) + (row.length - 1) * GAP_X;
  const width = Math.max(NODE_W, ...[...rows.values()].map(rowWidth));
  const placed: PlacedNode[] = [];
  const centers = new Map<string, { x: number; y: number }>();
  for (const [l, row] of rows) {
    row.sort((a, b) => a.sortKey.localeCompare(b.sortKey, "tr"));
    let x = (width - rowWidth(row)) / 2;
    const y = (maxLayer - l) * (NODE_H + GAP_Y);
    for (const slot of row) {
      if (slot.node) placed.push({ ...slot.node, layer: l, x, y });
      else centers.set(slot.id, { x: x + slot.w / 2, y: y + NODE_H / 2 });
      x += slot.w + GAP_X;
    }
  }
  const waypoints = new Map<string, { x: number; y: number }[]>();
  for (const [key, ids] of waypointIds) waypoints.set(key, ids.map((id) => centers.get(id)!));
  return { placed, waypoints, width, height: (maxLayer + 1) * NODE_H + maxLayer * GAP_Y };
}
