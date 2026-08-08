// Taramalar — liste + yeni tarama formu + veri tazeliği uyarısı.

import Link from "next/link";

import { ScreeningForm } from "@/components/screening-form";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";
import type { DatasetFreshness, ScreeningList } from "@/lib/screening";
import { STATUS_LABELS, TONE_CLASSES, riskHeadline } from "@/lib/screening";

export const dynamic = "force-dynamic";

async function safeJson<T>(path: string): Promise<T | null> {
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as T;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

export default async function ScreeningsPage() {
  const user = await getCurrentUser();
  const [list, freshness] = await Promise.all([
    safeJson<ScreeningList>("/screenings"),
    safeJson<DatasetFreshness>("/screenings/datasets"),
  ]);
  const canRun = user.role !== "auditor";

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Taramalar</h1>
        <p className="text-sm text-muted">
          Yaptırım, PEP ve MASAK dondurma listelerine karşı tarama.
        </p>
      </div>

      {/* Bayat veriyle yapılan tarama "temiz" görünür ama güvenilmezdir — uyarı
          sonuçlardan ÖNCE gösterilir. */}
      {freshness?.any_stale === true && (
        <div className="rounded-card border border-warning bg-surface p-4 text-sm text-warning">
          <strong className="font-semibold">Yaptırım verisi güncel değil.</strong>{" "}
          {freshness.datasets.length === 0
            ? "Veri kümesi senkronu henüz çalışmadı."
            : `Bazı listeler ${freshness.staleness_threshold_hours} saatten eski.`}{" "}
          Bu durumda "eşleşme yok" sonucu kesin kabul edilmemelidir.
        </div>
      )}

      {canRun && (
        <section className="rounded-card border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-semibold tracking-wide text-muted uppercase">
            Yeni tarama
          </h2>
          <ScreeningForm />
        </section>
      )}

      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">
          Geçmiş taramalar {list !== null && `(${list.total})`}
        </h2>
        {list === null || list.items.length === 0 ? (
          <p className="text-sm text-muted">Henüz tarama yapılmadı.</p>
        ) : (
          <ul className="divide-y divide-border">
            {list.items.map((screening) => {
              const headline = riskHeadline(screening);
              return (
                <li key={screening.id} className="py-3">
                  <Link href={`/screenings/${screening.id}`} className="block hover:opacity-80">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-sm font-medium text-fg">{screening.subject_name}</div>
                        <div className="mt-0.5 text-xs text-muted">
                          {formatDate(screening.created_at)} · {screening.subjects.length} özne ·{" "}
                          {STATUS_LABELS[screening.status]}
                        </div>
                      </div>
                      <span
                        className={`shrink-0 rounded-md border px-2 py-1 text-xs ${TONE_CLASSES[headline.tone]}`}
                      >
                        {headline.text}
                      </span>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
