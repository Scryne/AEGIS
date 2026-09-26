import Link from "next/link";

import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser, ROLE_LABELS } from "@/lib/server/user";
import type { Role } from "@/lib/server/user";
import type { EntityList } from "@/lib/entities";
import type { AuditEventPage } from "@/lib/reports";
import { ACTION_LABELS } from "@/lib/reports";
import type { DatasetFreshness, Screening, ScreeningList } from "@/lib/screening";
import { TONE_CLASSES, riskHeadline } from "@/lib/screening";

// Panel — uyum görevlisinin güne başladığı ekran. Sıra DESIGN.md'deki ilkeyle aynı:
// önce durum (bayat veri, bekleyen iş), sonra ayrıntı (kuyruk, son taramalar, etkinlik),
// en son yönetim (ekip, ayarlar). Tüm sayılar mevcut uçlardan türetilir; ayrı bir özet
// ucu yoktur, bu yüzden liste sınırı (100) aşıldığında sayaçlar "en az" okunmalıdır.

interface Member {
  user_id: string;
  email: string;
  full_name: string | null;
  role: string;
}

interface Setting {
  key: string;
  value: Record<string, unknown>;
}

const AUDIT_ROLES: Role[] = ["owner", "compliance_officer", "auditor"];

async function safeJson<T>(path: string): Promise<T | null> {
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as T;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

function needsReview(screening: Screening): boolean {
  return screening.status === "failed" || screening.summary.pending > 0;
}

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: string }) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold ${tone ?? "text-fg"}`}>{value}</div>
      <div className="mt-1 text-xs text-muted">{hint}</div>
    </div>
  );
}

export default async function DashboardPage() {
  const user = await getCurrentUser();
  const canReadAudit = AUDIT_ROLES.includes(user.role);
  const [screenings, entities, freshness, audit, members, settings] = await Promise.all([
    safeJson<ScreeningList>("/screenings?limit=100"),
    safeJson<EntityList>("/entities?limit=1"),
    safeJson<DatasetFreshness>("/screenings/datasets"),
    canReadAudit ? safeJson<AuditEventPage>("/audit/events?limit=6") : Promise.resolve(null),
    safeJson<Member[]>("/members"),
    safeJson<Setting[]>("/settings"),
  ]);
  const canWriteSettings = user.role === "owner" || user.role === "compliance_officer";

  const items = screenings?.items ?? [];
  const pending = items.reduce((sum, s) => sum + s.summary.pending, 0);
  const confirmed = items.reduce((sum, s) => sum + s.summary.confirmed, 0);
  const failed = items.filter((s) => s.status === "failed").length;
  // Acil (yüksek skorlu bekleyen) ve başarısız koşular kuyruğun başına.
  const queue = items
    .filter(needsReview)
    .sort(
      (a, b) =>
        Number(b.status === "failed") - Number(a.status === "failed") ||
        b.summary.flagged_pending - a.summary.flagged_pending ||
        b.summary.pending - a.summary.pending,
    );

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Panel</h1>
        <p className="text-sm text-muted">Bekleyen inceleme, son taramalar ve dosya etkinliği.</p>
      </div>

      {freshness?.any_stale === true && (
        <div role="status" className="rounded-card border border-warning bg-surface p-4 text-sm text-warning">
          <strong className="font-semibold">Yaptırım verisi güncel değil.</strong>{" "}
          {freshness.datasets.length === 0
            ? "Veri kümesi senkronu henüz çalışmadı."
            : `Bazı listeler ${freshness.staleness_threshold_hours} saatten eski.`}{" "}
          Bu sürede alınan "eşleşme yok" sonuçları kesin kabul edilmemelidir.
        </div>
      )}

      <section aria-label="Özet" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi
          label="İnceleme bekleyen"
          value={String(pending)}
          hint={pending > 0 ? `${queue.length} taramada` : "Kuyruk boş"}
          tone={pending > 0 ? "text-warning" : undefined}
        />
        <Kpi
          label="Onaylanmış eşleşme"
          value={String(confirmed)}
          hint="Analist tarafından doğrulanan"
          tone={confirmed > 0 ? "text-danger" : undefined}
        />
        <Kpi
          label="Kayıtlı varlık"
          value={String(entities?.total ?? "—")}
          hint="Şirket ve kişi"
        />
        <Kpi
          label="Tarama"
          value={String(screenings?.total ?? "—")}
          hint={failed > 0 ? `${failed} tanesi yapılamadı` : "Tümü tamamlandı"}
          tone={failed > 0 ? "text-danger" : undefined}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-card border border-border bg-surface p-5">
          <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">
            İnceleme kuyruğu
          </h2>
          {queue.length === 0 ? (
            <p className="text-sm text-muted">
              Karar bekleyen eşleşme yok. Yeni bir müşteri için{" "}
              <Link href="/screenings" className="text-primary underline underline-offset-2">
                tarama başlatın
              </Link>
              .
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {queue.slice(0, 6).map((screening) => {
                const headline = riskHeadline(screening);
                return (
                  <li key={screening.id} className="py-2.5">
                    <Link href={`/screenings/${screening.id}`} className="block hover:opacity-80">
                      <div className="truncate text-sm font-medium text-fg">{screening.subject_name}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                        <span className={`rounded border px-1.5 py-0.5 ${TONE_CLASSES[headline.tone]}`}>
                          {headline.text}
                        </span>
                        {formatDate(screening.created_at)}
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="rounded-card border border-border bg-surface p-5">
          <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">
            Son taramalar
          </h2>
          {items.length === 0 ? (
            <p className="text-sm text-muted">Henüz tarama yapılmadı.</p>
          ) : (
            <ul className="divide-y divide-border">
              {items.slice(0, 6).map((screening) => {
                const headline = riskHeadline(screening);
                return (
                  <li key={screening.id} className="py-2.5">
                    <Link
                      href={`/screenings/${screening.id}`}
                      className="flex items-start justify-between gap-3 hover:opacity-80"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm text-fg">{screening.subject_name}</span>
                        <span className="text-xs text-muted">{formatDate(screening.created_at)}</span>
                      </span>
                      <span
                        className={`shrink-0 rounded border px-1.5 py-0.5 text-xs ${TONE_CLASSES[headline.tone]}`}
                      >
                        {headline.text}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      {audit !== null && (
        <section className="rounded-card border border-border bg-surface p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">Son etkinlik</h2>
            <Link href="/audit" className="text-xs text-primary underline underline-offset-2">
              Denetim izinin tamamı
            </Link>
          </div>
          {audit.items.length === 0 ? (
            <p className="text-sm text-muted">Henüz kayıtlı eylem yok.</p>
          ) : (
            <ul className="divide-y divide-border">
              {audit.items.map((event) => (
                <li key={event.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="min-w-0 truncate text-fg">
                    {ACTION_LABELS[event.action] ?? event.action}
                    {event.actor_label !== null && (
                      <span className="text-muted"> · {event.actor_label}</span>
                    )}
                  </span>
                  <span className="shrink-0 text-xs text-muted">{formatDate(event.occurred_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-card border border-border bg-surface p-5">
          <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">Ekip</h2>
          <ul className="divide-y divide-border">
            {(members ?? []).map((m) => (
              <li key={m.user_id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className="min-w-0 truncate text-fg">{m.full_name ?? m.email}</span>
                <span className="shrink-0 text-muted">{ROLE_LABELS[m.role as Role] ?? m.role}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-card border border-border bg-surface p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">
              Kiracı ayarları
            </h2>
            <span className="text-xs text-muted">
              {canWriteSettings ? "Yazma yetkiniz var" : "Salt-okunur"}
            </span>
          </div>
          {settings === null || settings.length === 0 ? (
            <p className="text-sm text-muted">
              Varsayılan eşikler ve saklama süreleri kullanılıyor.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {settings.map((s) => (
                <li key={s.key} className="py-2 text-sm">
                  <span className="font-mono text-fg">{s.key}</span>
                  <span className="mt-0.5 block font-mono text-xs break-all text-muted">
                    {JSON.stringify(s.value)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
