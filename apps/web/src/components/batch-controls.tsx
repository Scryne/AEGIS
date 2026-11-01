"use client";

// Toplu iş denetimleri ve sonuç tablosu (E3.3). Kurallar backend'dedir; burada yalnız
// rolün görebileceği düğmeler gösterilir, sunucunun hata mesajı olduğu gibi aktarılır.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  RESOLUTION_LABELS,
  ROW_STATUS_LABELS,
  ROW_STATUS_TONE,
  rowRisk,
  type BatchRow,
  type BatchStatus,
} from "@/lib/batches";

async function post(url: string, body?: unknown): Promise<{ ok: boolean; data: unknown }> {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => null);
    return { ok: res.ok, data };
  } catch {
    return { ok: false, data: { error: { message: "Sunucuya ulaşılamadı." } } };
  }
}

function message(data: unknown, fallback: string): string {
  return (data as { error?: { message?: string } } | null)?.error?.message ?? fallback;
}

/** İş sürerken sayfayı birkaç saniyede bir tazeler (worker ilerlemesi görünsün). */
export function BatchAutoRefresh({ status }: { status: BatchStatus }) {
  const router = useRouter();
  useEffect(() => {
    if (status !== "queued" && status !== "running") return;
    const t = setInterval(() => router.refresh(), 4000);
    return () => clearInterval(t);
  }, [status, router]);
  return null;
}

export function BatchControls({
  batchId,
  status,
  pending,
  failed,
  canRunNow,
}: {
  batchId: string;
  status: BatchStatus;
  pending: number;
  failed: number;
  canRunNow: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(path: string, done: (d: unknown) => string | null) {
    setBusy(true);
    setError(null);
    setNote(null);
    const r = await post(`/api/v1/batches/${batchId}/${path}`);
    setBusy(false);
    if (!r.ok) {
      setError(message(r.data, "İşlem yapılamadı."));
      return;
    }
    setNote(done(r.data));
    router.refresh();
  }

  const active = status === "queued" || status === "running";
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {status === "draft" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => act("start", () => "Başlatıldı; satırlar arka planda işleniyor.")}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-fg disabled:opacity-50"
          >
            Taramayı başlat ({pending} satır)
          </button>
        )}
        {active && canRunNow && pending > 0 && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              act("process", (d) => {
                const r = d as { processed: number; remaining: number };
                return `${r.processed} satır işlendi, ${r.remaining} kaldı.`;
              })
            }
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-fg disabled:opacity-50"
          >
            {busy ? "İşleniyor…" : "Şimdi işle (25 satır)"}
          </button>
        )}
        {failed > 0 && status !== "draft" && status !== "cancelled" && (
          <button
            type="button"
            disabled={busy}
            onClick={() => act("retry", () => "Başarısız satırlar yeniden sıraya alındı.")}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-fg disabled:opacity-50"
          >
            Başarısızları yeniden dene ({failed})
          </button>
        )}
        {(status === "draft" || active) && (
          <button
            type="button"
            disabled={busy}
            onClick={() => act("cancel", () => "İptal edildi; bekleyen satırlar taranmayacak.")}
            className="rounded-md px-3 py-1.5 text-sm text-muted hover:text-danger disabled:opacity-50"
          >
            İptal et
          </button>
        )}
        {status !== "draft" && (
          <a
            href={`/api/v1/batches/${batchId}/export.csv`}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-fg"
          >
            Sonuç özetini indir (CSV)
          </a>
        )}
      </div>
      {note && (
        <p role="status" className="text-sm text-muted">
          {note}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

function ResolveRow({ batchId, row }: { batchId: string; row: BatchRow }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function resolve(entityId: string | null) {
    setBusy(true);
    setError(null);
    const r = await post(`/api/v1/batches/${batchId}/rows/${row.id}/resolve`, { entity_id: entityId });
    setBusy(false);
    if (!r.ok) {
      setError(message(r.data, "Karar kaydedilemedi."));
      return;
    }
    router.refresh();
  }
  return (
    <div className="mt-2 space-y-2 rounded-md border border-warning bg-warning/5 p-3">
      <p className="text-xs text-fg">
        Kütükte benzer kayıt var; aynı müşteri mi? Seçtiğiniz kayıt taranır.
      </p>
      <ul className="space-y-1">
        {(row.resolution_candidates ?? []).map((c) => (
          <li key={c.entity_id} className="flex flex-wrap items-center gap-2 text-xs">
            <button
              type="button"
              disabled={busy || c.conflicting_identifier !== null}
              onClick={() => resolve(c.entity_id)}
              className="rounded border border-border bg-surface px-2 py-1 font-medium text-fg disabled:opacity-50"
            >
              Bu kayıt
            </button>
            <Link href={`/entities/${c.entity_id}`} className="text-fg underline">
              {c.name}
            </Link>
            <span className="text-muted">· {c.reason}</span>
          </li>
        ))}
      </ul>
      <button
        type="button"
        disabled={busy}
        onClick={() => resolve(null)}
        className="rounded border border-border bg-surface px-2 py-1 text-xs font-medium text-fg disabled:opacity-50"
      >
        Hiçbiri: yeni varlık aç
      </button>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function BatchRowsTable({
  batchId,
  rows,
  canWrite,
}: {
  batchId: string;
  rows: BatchRow[];
  canWrite: boolean;
}) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selectable = rows.filter((r) => r.status === "done" && r.entity_id);

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  async function bulk(action: "monitor" | "open_case") {
    setBusy(true);
    setError(null);
    setNote(null);
    const r = await post(`/api/v1/batches/${batchId}/bulk`, { action, row_ids: [...selected] });
    setBusy(false);
    if (!r.ok) {
      setError(message(r.data, "Toplu işlem yapılamadı."));
      return;
    }
    const d = r.data as { applied: number; skipped: number };
    setNote(
      `${d.applied} kayda uygulandı${d.skipped ? `, ${d.skipped} kayıt atlandı (zaten uygulanmış ya da taranmamış)` : ""}.`,
    );
    setSelected(new Set());
    router.refresh();
  }

  return (
    <div className="space-y-3">
      {canWrite && selectable.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">{selected.size} satır seçili</span>
          <button
            type="button"
            disabled={busy || selected.size === 0}
            onClick={() => bulk("open_case")}
            className="rounded-md border border-border px-3 py-1.5 font-medium text-fg disabled:opacity-50"
          >
            Seçilenler için vaka aç
          </button>
          <button
            type="button"
            disabled={busy || selected.size === 0}
            onClick={() => bulk("monitor")}
            className="rounded-md border border-border px-3 py-1.5 font-medium text-fg disabled:opacity-50"
          >
            Seçilenleri izlemeye al
          </button>
        </div>
      )}
      {note && (
        <p role="status" className="text-sm text-muted">
          {note}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="overflow-x-auto rounded-card border border-border bg-surface">
        <table className="w-full min-w-[44rem] text-left text-sm">
          <caption className="sr-only">Toplu tarama sonuçları</caption>
          <thead className="bg-bg text-xs text-muted">
            <tr>
              {canWrite && (
                <th className="w-10 px-3 py-2">
                  <span className="sr-only">Seç</span>
                </th>
              )}
              <th className="px-3 py-2 font-medium">Satır</th>
              <th className="px-3 py-2 font-medium">Ad / unvan</th>
              <th className="px-3 py-2 font-medium">Sonuç</th>
              <th className="px-3 py-2 text-right font-medium">Aday</th>
              <th className="px-3 py-2 text-right font-medium">En yüksek</th>
              <th className="px-3 py-2 font-medium">Durum</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((r) => {
              const risk = rowRisk(r);
              const canSelect = canWrite && r.status === "done" && r.entity_id;
              return (
                <tr key={r.id} className="align-top">
                  {canWrite && (
                    <td className="px-3 py-2">
                      {canSelect && (
                        <input
                          type="checkbox"
                          aria-label={`${r.row_no}. satırı seç`}
                          checked={selected.has(r.id)}
                          onChange={() => toggle(r.id)}
                          className="size-4"
                        />
                      )}
                    </td>
                  )}
                  <td className="px-3 py-2 font-mono text-xs text-muted tabular-nums">{r.row_no}</td>
                  <td className="px-3 py-2">
                    {r.entity_id ? (
                      <Link href={`/entities/${r.entity_id}`} className="font-medium text-fg underline">
                        {r.data.name}
                      </Link>
                    ) : (
                      <span className="font-medium text-fg">{r.data.name || "—"}</span>
                    )}
                    <span className="block text-xs text-muted">
                      {r.data.schema_type === "Person" ? "Kişi" : "Şirket"}
                      {r.data.tax_number && ` · VKN ${r.data.tax_number}`}
                      {r.data.external_ref && ` · ${r.data.external_ref}`}
                      {r.resolution && ` · ${RESOLUTION_LABELS[r.resolution] ?? r.resolution}`}
                    </span>
                    {r.status === "needs_review" && canWrite && <ResolveRow batchId={batchId} row={r} />}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium ${risk.tone}`}>
                      {risk.label}
                    </span>
                    {r.screening_id && (
                      <Link href={`/screenings/${r.screening_id}`} className="mt-1 block text-xs text-primary underline">
                        Taramayı aç
                      </Link>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">{r.candidate_count ?? "—"}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">
                    {r.top_score != null ? r.top_score.toFixed(2) : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs ${ROW_STATUS_TONE[r.status]}`}>
                      {ROW_STATUS_LABELS[r.status]}
                    </span>
                    {(r.errors.length > 0 || r.error || r.duplicate_of) && (
                      <span className="mt-1 block max-w-56 text-xs text-muted">
                        {r.errors.join(" ") || r.error || `${r.duplicate_of}. satırın tekrarı`}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
