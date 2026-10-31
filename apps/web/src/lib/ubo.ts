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

export const NODE_W = 168;
export const NODE_H = 52;
const GAP_X = 28;
const GAP_Y = 64;

/**
 * Katmanlı yerleşim: hedef en altta (katman 0), sahipler yukarıda. Bir düğümün katmanı,
 * hedefe giden en uzun döngüsüz yolun uzunluğudur; böylece her ok yukarıdan aşağı akar.
 * Döngüdeki kenarlar katman hesabında yok sayılır (onlar ayrıca kesikli çizilir).
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

  const maxLayer = Math.max(0, ...layer.values());
  const rows = new Map<number, UboNode[]>();
  for (const node of nodes) {
    const l = layer.get(node.id) ?? 0;
    rows.set(l, [...(rows.get(l) ?? []), node]);
  }
  const widest = Math.max(1, ...[...rows.values()].map((r) => r.length));
  const width = widest * NODE_W + (widest - 1) * GAP_X;
  const placed: PlacedNode[] = [];
  for (const [l, row] of rows) {
    row.sort((a, b) => a.name.localeCompare(b.name, "tr"));
    const rowWidth = row.length * NODE_W + (row.length - 1) * GAP_X;
    const start = (width - rowWidth) / 2;
    row.forEach((node, i) =>
      placed.push({ ...node, layer: l, x: start + i * (NODE_W + GAP_X), y: (maxLayer - l) * (NODE_H + GAP_Y) }),
    );
  }
  return { placed, width, height: (maxLayer + 1) * NODE_H + maxLayer * GAP_Y };
}
