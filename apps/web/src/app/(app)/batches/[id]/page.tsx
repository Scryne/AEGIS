// Toplu iş sonucu (E3.3): önce ilerleme ve risk özeti, sonra riske göre sıralı satırlar.
// Riskli satırlar için toplu vaka/izleme; belirsiz eşleşmede insan kararı burada verilir.

import Link from "next/link";
import { notFound } from "next/navigation";

import { BatchAutoRefresh, BatchControls, BatchRowsTable } from "@/components/batch-controls";
import { BATCH_STATUS_LABELS, type Batch, type BatchRow } from "@/lib/batches";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";

export const dynamic = "force-dynamic";

const FILTERS = [
  { key: "all", label: "Tümü", query: {} },
  { key: "hits", label: "Adayı olanlar", query: { hits: "true" } },
  { key: "review", label: "Karar bekleyen", query: { status: "needs_review" } },
  { key: "failed", label: "Başarısız", query: { status: "failed" } },
  { key: "invalid", label: "Geçersiz / tekrar", query: { status: "invalid,duplicate" } },
] as const;

const SORTS = [
  { key: "risk", label: "Riske göre" },
  { key: "row", label: "Dosya sırasıyla" },
  { key: "name", label: "Ada göre" },
] as const;

export default async function BatchDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ filter?: string; sort?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const filter = FILTERS.find((f) => f.key === sp.filter) ?? FILTERS[0];
  const sort = SORTS.find((s) => s.key === sp.sort) ?? SORTS[0];
  const user = await getCurrentUser();

  const res = await serverFetch(`/batches/${id}`);
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error("Toplu iş yüklenemedi.");
  const batch = (await res.json()) as Batch;
  const q = new URLSearchParams({ ...filter.query, sort: sort.key, limit: "500" });
  const rowsRes = await serverFetch(`/batches/${id}/rows?${q}`);
  const rows = rowsRes.ok ? ((await rowsRes.json()) as { items: BatchRow[]; total: number }) : null;

  const c = batch.counts;
  const workable = c.pending + c.done + c.needs_review + c.failed + c.cancelled;
  const finished = c.done + c.failed + c.needs_review + c.cancelled;
  const pct = workable ? Math.round((finished / workable) * 100) : 0;
  const canWrite = user.role !== "auditor";
  const canRunNow = user.role === "owner" || user.role === "compliance_officer";
  const href = (f: string, s: string) => `/batches/${id}?filter=${f}&sort=${s}`;
  const tiles: [string, number, string][] = [
    ["Tarandı", c.done, "text-fg"],
    ["Yaptırım adayı", batch.risk.sanction_rows, batch.risk.sanction_rows ? "text-danger" : "text-fg"],
    ["PEP adayı", batch.risk.pep_rows, batch.risk.pep_rows ? "text-warning" : "text-fg"],
    ["Karar bekleyen", c.needs_review, c.needs_review ? "text-warning" : "text-fg"],
    ["Başarısız", c.failed, c.failed ? "text-danger" : "text-fg"],
    ["Geçersiz / tekrar", c.invalid + c.duplicate, "text-fg"],
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <BatchAutoRefresh status={batch.status} />
      <div className="space-y-1">
        <Link href="/batches" className="text-xs text-muted underline">
          ← Toplu tarama
        </Link>
        <h1 className="text-2xl font-semibold break-all text-fg">{batch.file_name}</h1>
        <p className="text-sm text-muted">
          {BATCH_STATUS_LABELS[batch.status]}
          {batch.status === "completed" && c.failed > 0 && (
            <span className="text-danger"> ({c.failed} satır başarısız)</span>
          )}{" "}
          · {batch.total_rows} satır · yüklendi{" "}
          {new Date(batch.created_at).toLocaleString("tr-TR")}
        </p>
      </div>

      <section aria-labelledby="ozet-baslik" className="space-y-4 rounded-card border border-border bg-surface p-5">
        <h2 id="ozet-baslik" className="sr-only">
          İlerleme ve özet
        </h2>
        {batch.status !== "draft" && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted">
              <span>İlerleme</span>
              <span className="font-mono tabular-nums">
                {finished}/{workable}
              </span>
            </div>
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              aria-label="Toplu iş ilerlemesi"
              className="h-2 overflow-hidden rounded-full bg-bg"
            >
              <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-6">
          {tiles.map(([label, value, tone]) => (
            <div key={label}>
              <dt className="text-xs text-muted">{label}</dt>
              <dd className={`font-mono text-xl tabular-nums ${tone}`}>{value}</dd>
            </div>
          ))}
        </dl>
        {canWrite && (
          <div className="border-t border-border pt-4">
            <BatchControls
              batchId={batch.id}
              status={batch.status}
              pending={c.pending}
              failed={c.failed}
              canRunNow={canRunNow}
            />
          </div>
        )}
      </section>

      <section aria-labelledby="satir-baslik" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="satir-baslik" className="text-sm font-semibold tracking-wide text-muted uppercase">
            Satırlar {rows && <span className="font-mono normal-case">({rows.total})</span>}
          </h2>
          <nav aria-label="Sıralama" className="flex gap-1 text-xs">
            {SORTS.map((s) => (
              <Link
                key={s.key}
                href={href(filter.key, s.key)}
                aria-current={sort.key === s.key ? "page" : undefined}
                className={`rounded-md px-2 py-1 ${
                  sort.key === s.key ? "bg-surface font-medium text-primary shadow-sm" : "text-muted hover:text-fg"
                }`}
              >
                {s.label}
              </Link>
            ))}
          </nav>
        </div>
        <nav aria-label="Satır süzgeci" className="flex gap-1 overflow-x-auto">
          {FILTERS.map((f) => (
            <Link
              key={f.key}
              href={href(f.key, sort.key)}
              aria-current={filter.key === f.key ? "page" : undefined}
              className={`shrink-0 rounded-md px-3 py-1.5 text-sm whitespace-nowrap ${
                filter.key === f.key ? "bg-surface font-medium text-primary shadow-sm" : "text-muted hover:text-fg"
              }`}
            >
              {f.label}
            </Link>
          ))}
        </nav>
        {rows === null ? (
          <p role="alert" className="text-sm text-danger">
            Satırlar yüklenemedi.
          </p>
        ) : rows.items.length === 0 ? (
          <p className="rounded-card border border-border bg-surface p-6 text-center text-sm text-muted">
            Bu süzgeçte satır yok.
          </p>
        ) : (
          <BatchRowsTable batchId={batch.id} rows={rows.items} canWrite={canWrite} />
        )}
      </section>
    </div>
  );
}
