// Toplu tarama (E3.3): CSV yükle, sütunları eşle, önizlemeyi doğrula, başlat.
// Satırlar kütükle çözümlenir (aynı müşteri iki kez açılmaz), her biri kendi taramasını alır.

import Link from "next/link";

import { BatchUpload } from "@/components/batch-upload";
import { BATCH_STATUS_LABELS, type Batch } from "@/lib/batches";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";

export const dynamic = "force-dynamic";

export default async function BatchesPage() {
  const user = await getCurrentUser();
  const res = await serverFetch("/batches?limit=50");
  const data = res.ok ? ((await res.json()) as { items: Batch[] }) : null;
  const canWrite = user.role !== "auditor";

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Toplu tarama</h1>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Müşteri listenizi CSV olarak yükleyin. Her satır kütükteki kayıtla eşleştirilir (vergi no ya
          da ad), yoksa yeni varlık açılır, sonra yaptırım ve PEP listelerinde taranır. Kütükte birden
          çok benzer kayıt varsa satır taranmadan size sorulur. Her satır aylık sorgu hakkınızdan düşer.
        </p>
      </div>

      {canWrite && (
        <section aria-labelledby="yeni-baslik" className="rounded-card border border-border bg-surface p-5">
          <h2 id="yeni-baslik" className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">
            Yeni toplu iş
          </h2>
          <BatchUpload />
        </section>
      )}

      <section aria-labelledby="gecmis-baslik" className="space-y-3">
        <h2 id="gecmis-baslik" className="text-sm font-semibold tracking-wide text-muted uppercase">
          Toplu işler
        </h2>
        {data === null ? (
          <p role="alert" className="rounded-card border border-danger bg-surface p-4 text-sm text-danger">
            Toplu işler yüklenemedi.
          </p>
        ) : data.items.length === 0 ? (
          <p className="rounded-card border border-border bg-surface p-6 text-center text-sm text-muted">
            Henüz toplu iş yok.
          </p>
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-card border border-border bg-surface">
            {data.items.map((b) => (
              <li key={b.id}>
                <Link
                  href={`/batches/${b.id}`}
                  className="grid gap-1 px-5 py-4 hover:bg-bg sm:grid-cols-[1fr_auto] sm:items-center"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-fg">{b.file_name}</p>
                    <p className="text-xs text-muted">
                      {new Date(b.created_at).toLocaleString("tr-TR")} · {b.total_rows} satır ·{" "}
                      {b.counts.done} tarandı
                      {b.risk.sanction_rows > 0 && (
                        <span className="text-danger"> · {b.risk.sanction_rows} yaptırım adayı</span>
                      )}
                    </p>
                  </div>
                  <span className="text-xs text-muted">{BATCH_STATUS_LABELS[b.status]}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
