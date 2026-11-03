"use client";

// Gerçek faydalanıcı paneli (E2.1): sahiplik grafı, UBO yolları, belirsizliğin nedeni.
//
// Grafın amacı süs değil denetim: hangi kişinin hangi zincirle ve ne kadar etkin payla
// UBO sayıldığı, zincirin nerede koptuğu ve döngünün nerede olduğu tek bakışta görünmeli.
// UBO yollarındaki oklar ana renkte, döngüyü kapatan oklar kesikli kırmızı, kontrol ve
// yönetici bağları noktalı griyle çizilir. Her düğüm kendi kaydına götürür.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import type { UboComputation } from "@/lib/ubo";
import { BASIS_LABELS, NODE_H, NODE_W, STATUS_LABELS, layout } from "@/lib/ubo";

const STATUS_TONE: Record<UboComputation["status"], string> = {
  determined: "border-success/40 bg-success-soft text-success",
  not_determinable: "border-danger/40 bg-danger-soft text-danger",
  none_found: "border-warning/40 bg-warning-soft text-warning",
};

function clip(text: string, max = 22): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function UboGraph({ data, target }: { data: UboComputation; target: string }) {
  const { placed, width, height } = useMemo(
    () => layout(target, data.nodes, data.edges),
    [target, data.nodes, data.edges],
  );
  const byId = new Map(placed.map((n) => [n.id, n]));
  const uboIds = new Set(data.ubos.map((u) => u.entity_id));
  const unresolvedIds = new Set(data.unresolved.map((u) => u.entity_id));
  const pathEdges = new Set<string>();
  for (const ubo of data.ubos)
    for (const path of ubo.paths)
      for (let i = 0; i + 1 < path.length; i++) pathEdges.add(`${path[i]}>${path[i + 1]}`);
  const cycleEdges = new Set<string>();
  for (const cycle of data.cycles)
    for (let i = 0; i + 1 < cycle.length; i++) cycleEdges.add(`${cycle[i]}>${cycle[i + 1]}`);
  const share = new Map(data.ubos.map((u) => [u.entity_id, u.effective_percent]));

  const pad = 12;
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-bg p-2">
      <svg
        role="img"
        aria-label="Sahiplik grafı"
        width={width + pad * 2}
        height={height + pad * 2}
        viewBox={`${-pad} ${-pad} ${width + pad * 2} ${height + pad * 2}`}
        className="mx-auto block"
      >
        <defs>
          {["muted", "primary", "danger"].map((tone) => (
            <marker
              key={tone}
              id={`ok-${tone}`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,5 L0,10 z" fill={`var(--color-${tone})`} />
            </marker>
          ))}
        </defs>
        {data.edges.map((edge) => {
          const from = byId.get(edge.owner);
          const to = byId.get(edge.owned);
          if (!from || !to) return null;
          const key = `${edge.owner}>${edge.owned}`;
          const onPath = edge.kind === "ownership" && pathEdges.has(key);
          const inCycle = cycleEdges.has(key);
          const tone = inCycle ? "danger" : onPath ? "primary" : "muted";
          const x1 = from.x + NODE_W / 2;
          const x2 = to.x + NODE_W / 2;
          const upward = from.layer <= to.layer;
          const y1 = upward ? from.y : from.y + NODE_H;
          const y2 = upward ? to.y + NODE_H : to.y;
          // Döngüyü kapatan (yukarı dönen) ok eğri çizilir; etiketi eğrinin kendi orta
          // noktasına konur, yoksa aynı iki düğüm arasındaki düz okun etiketiyle çakışır.
          const c1 = { x: x1 + 70, y: y1 - 50 };
          const c2 = { x: x2 + 70, y: y2 + 50 };
          const midX = upward ? (x1 + 3 * c1.x + 3 * c2.x + x2) / 8 : (x1 + x2) / 2;
          const midY = upward ? (y1 + 3 * c1.y + 3 * c2.y + y2) / 8 : (y1 + y2) / 2;
          const d = upward
            ? `M${x1},${y1} C${c1.x},${c1.y} ${c2.x},${c2.y} ${x2},${y2}`
            : `M${x1},${y1} L${x2},${y2}`;
          const label =
            edge.kind === "ownership"
              ? edge.percent === null
                ? "pay ?"
                : `%${Number(edge.percent).toLocaleString("tr-TR", { maximumFractionDigits: 2 })}`
              : edge.kind === "control"
                ? "kontrol"
                : "yönetici";
          return (
            <g key={`${key}-${edge.relationship_id ?? edge.kind}`}>
              <path
                d={d}
                fill="none"
                stroke={`var(--color-${tone})`}
                strokeWidth={onPath ? 2 : 1.25}
                strokeDasharray={inCycle ? "6 4" : edge.kind === "ownership" ? undefined : "2 4"}
                markerEnd={`url(#ok-${tone})`}
              />
              <rect x={midX - 26} y={midY - 9} width={52} height={18} rx={9} fill="var(--color-surface)" stroke="var(--color-border)" />
              <text x={midX} y={midY + 4} textAnchor="middle" className="fill-fg font-mono text-[10px]">
                {label}
              </text>
            </g>
          );
        })}
        {placed.map((node) => {
          const isTarget = node.id === target;
          const isUbo = uboIds.has(node.id);
          const isUnresolved = unresolvedIds.has(node.id);
          const stroke = isUbo
            ? "var(--color-primary)"
            : isUnresolved
              ? "var(--color-warning)"
              : isTarget
                ? "var(--color-fg)"
                : "var(--color-border)";
          const sub =
            node.schema === "Person"
              ? isUbo
                ? `UBO · %${Number(share.get(node.id) ?? 0).toLocaleString("tr-TR", { maximumFractionDigits: 2 })}`
                : "Gerçek kişi"
              : `Şirket${node.country ? ` · ${node.country}` : ""}`;
          return (
            <a key={node.id} href={`/entities/${node.id}`} aria-label={`${node.name} kaydını aç`}>
              <rect
                x={node.x}
                y={node.y}
                width={NODE_W}
                height={NODE_H}
                rx={node.schema === "Person" ? 26 : 8}
                fill="var(--color-surface)"
                stroke={stroke}
                strokeWidth={isUbo || isTarget ? 2 : 1.25}
                strokeDasharray={isUnresolved ? "5 3" : undefined}
              />
              <title>{node.name}</title>
              <text x={node.x + NODE_W / 2} y={node.y + 22} textAnchor="middle" className="fill-fg text-[12px] font-medium">
                {clip(node.name)}
              </text>
              <text x={node.x + NODE_W / 2} y={node.y + 38} textAnchor="middle" className="fill-muted text-[10px]">
                {sub}
              </text>
            </a>
          );
        })}
      </svg>
    </div>
  );
}

export function UboPanel({
  entityId,
  computation,
  canWrite,
}: {
  entityId: string;
  computation: UboComputation | null;
  canWrite: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const names = new Map((computation?.nodes ?? []).map((n) => [n.id, n.name]));

  async function compute() {
    setBusy("compute");
    setError(null);
    try {
      const res = await fetch(`/api/v1/entities/${entityId}/ubo`, { method: "POST" });
      if (!res.ok) {
        const payload = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
        setError(payload?.error?.message ?? "Hesap yapılamadı.");
        return;
      }
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(null);
    }
  }

  async function screen(personId: string) {
    setBusy(personId);
    setError(null);
    try {
      const res = await fetch(`/api/v1/screenings/from-entity/${personId}`, { method: "POST" });
      const payload = (await res.json().catch(() => null)) as
        | { id?: string; error?: { message?: string } }
        | null;
      if (res.ok || (res.status === 502 && payload?.id)) {
        router.push(`/screenings/${payload?.id}`);
        return;
      }
      setError(payload?.error?.message ?? "Tarama başlatılamadı.");
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(null);
    }
  }

  const thresholdText = computation
    ? `%${computation.threshold_percent}${computation.inclusive ? " ve üzeri" : "'ten fazla"}`
    : "%25'ten fazla";

  return (
    <section className="space-y-4 panel p-5" aria-labelledby="ubo-baslik">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="ubo-baslik" className="eyebrow">
            Gerçek faydalanıcı
          </h2>
          <p className="mt-1 text-xs text-muted">
            Sahiplik zincirindeki paylar katman katman çarpılır; eşik {thresholdText}. Kimse
            eşiği aşmıyorsa kontrol sahipleri, o da yoksa üst düzey yöneticiler gösterilir.
          </p>
        </div>
        {canWrite && (
          <button
            type="button"
            onClick={compute}
            disabled={busy !== null}
            className="btn-primary"
          >
            {busy === "compute" ? "Hesaplanıyor…" : computation ? "Yeniden hesapla" : "UBO'yu hesapla"}
          </button>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {computation === null ? (
        <p className="text-sm text-muted">
          Henüz hesap yapılmadı. Ortakları pay yüzdesiyle kaydedin (bağlar bölümü), sonra hesaplayın.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-full border px-2 py-0.5 font-medium ${STATUS_TONE[computation.status]}`}>
              {STATUS_LABELS[computation.status]}
            </span>
            <span className="text-muted">
              {new Date(computation.created_at).toLocaleString("tr-TR")} · girdi özeti{" "}
              <span className="font-mono">{computation.input_sha256.slice(0, 12)}</span>
            </span>
            {Number(computation.unattributed_percent) > 0 && (
              <span className="text-muted">
                · kimseye bağlanamayan pay %
                {Number(computation.unattributed_percent).toLocaleString("tr-TR", { maximumFractionDigits: 2 })}
              </span>
            )}
          </div>

          {computation.nodes.length > 1 && <UboGraph data={computation} target={entityId} />}

          {computation.ubos.length > 0 && (
            <ul className="divide-y divide-border">
              {computation.ubos.map((ubo) => (
                <li key={ubo.entity_id} className="flex flex-wrap items-start justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <Link href={`/entities/${ubo.entity_id}`} className="text-sm font-medium text-fg underline">
                      {ubo.name}
                    </Link>
                    <div className="text-xs text-muted">
                      {BASIS_LABELS[ubo.basis]}
                      {ubo.basis === "ownership" &&
                        ` · etkin pay %${Number(ubo.effective_percent).toLocaleString("tr-TR", { maximumFractionDigits: 4 })}`}
                    </div>
                    {ubo.paths.map((path) => (
                      <div key={path.join(">")} className="text-xs text-muted">
                        {path.map((id) => names.get(id) ?? id).join(" → ")}
                      </div>
                    ))}
                  </div>
                  {computation.unscreened_ubo_ids.includes(ubo.entity_id) && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-warning">Henüz taranmadı</span>
                      {canWrite && (
                        <button
                          type="button"
                          onClick={() => screen(ubo.entity_id)}
                          disabled={busy !== null}
                          className="rounded-md border border-border px-2 py-1 text-xs text-fg hover:border-primary disabled:opacity-60"
                        >
                          {busy === ubo.entity_id ? "Taranıyor…" : "Tara"}
                        </button>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {(computation.unresolved.length > 0 || computation.cycles.length > 0) && (
            <div className="space-y-2 rounded-card border border-warning p-3 text-sm">
              <p className="font-medium text-fg">Zincirin çözülemeyen kısmı</p>
              <ul className="space-y-1 text-xs text-muted">
                {computation.unresolved.map((item) => (
                  <li key={`${item.entity_id}-${item.reason}`}>
                    <Link href={`/entities/${item.entity_id}`} className="text-fg underline">
                      {item.name}
                    </Link>
                    : {item.reason}
                    {item.share_percent !== null &&
                      ` (etkin pay %${Number(item.share_percent).toLocaleString("tr-TR", { maximumFractionDigits: 2 })})`}
                  </li>
                ))}
                {computation.cycles.map((cycle) => (
                  <li key={cycle.join(">")} className="text-danger">
                    Döngüsel ortaklık: {cycle.map((id) => names.get(id) ?? id).join(" → ")}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-muted">
                Belirlenemeyen pay, MASAK açısından kendi başına bir işarettir; eksik ortaklık
                bilgisini isteyip kaydettikten sonra yeniden hesaplayın.
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
