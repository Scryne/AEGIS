// ŞİB taslakları (E2.2): uyum görevlisinin MASAK Online'a girmeden önce hazırladığı bildirimler.
//
// Yalnız sahip ve uyum görevlisi görür; diğer rollere sayfa yerine bir açıklama gösterilir
// (backend zaten 403 döner). Taslak burada açılmaz: varlık sayfasından, dosyanın bağlamında açılır.

import Link from "next/link";

import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";
import {
  GIZLILIK_NOTU,
  SIB_ROLES,
  SIB_STATUS_LABELS,
  SIB_STATUS_TONE,
  SORUMLULUK_NOTU,
  type SibOzet,
} from "@/lib/sib";

export const dynamic = "force-dynamic";

export default async function SibListPage() {
  const user = await getCurrentUser();
  if (!(SIB_ROLES as readonly string[]).includes(user.role)) {
    return (
      <div className="mx-auto max-w-2xl rounded-card border border-border bg-surface p-6 text-sm text-muted">
        Bu sayfa yalnız sahip ve uyum görevlisi rolüne açıktır.
      </div>
    );
  }
  const res = await serverFetch("/sib-drafts?limit=200");
  const data = res.ok ? ((await res.json()) as { items: SibOzet[] }) : null;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Şüpheli işlem bildirimi taslakları</h1>
        <p className="mt-1 max-w-prose text-sm text-muted">{SORUMLULUK_NOTU}</p>
      </div>

      <div role="note" className="rounded-card border border-danger bg-surface p-4 text-sm text-danger">
        <strong className="font-semibold">Gizli.</strong> {GIZLILIK_NOTU}
      </div>

      {data === null ? (
        <p className="rounded-card border border-danger bg-surface p-4 text-sm text-danger">
          Taslaklar yüklenemedi. Sayfayı yenileyin; sorun sürerse API&apos;nin çalıştığını kontrol edin.
        </p>
      ) : data.items.length === 0 ? (
        <div className="rounded-card border border-border bg-surface p-8 text-center">
          <p className="text-sm font-medium text-fg">Henüz taslak yok.</p>
          <p className="mt-1 text-xs text-muted">
            Taslak, varlık sayfasındaki &quot;ŞİB taslağı hazırla&quot; düğmesiyle dosyadan ön
            doldurularak açılır.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border rounded-card border border-border bg-surface">
          {data.items.map((t) => (
            <li key={t.id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <Link href={`/sib/${t.id}`} className="font-mono text-sm font-medium text-fg underline">
                  {t.reference_no}
                </Link>
                <p className="truncate text-sm text-fg">{t.entity_name}</p>
                <p className="text-xs text-muted">
                  Son değişiklik {new Date(t.updated_at).toLocaleString("tr-TR")}
                  {t.export_count > 0 && ` · ${t.export_count} kez dışa aktarıldı`}
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                {t.status !== "iptal" && t.errors > 0 && (
                  <span className="text-xs text-danger">{t.errors} eksik</span>
                )}
                <span
                  className={`rounded-full border px-2 py-0.5 text-xs font-medium ${SIB_STATUS_TONE[t.status]}`}
                >
                  {SIB_STATUS_LABELS[t.status]}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
