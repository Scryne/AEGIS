import { ArrowRight, ShieldAlert } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { StatTile } from "@/components/stat-tile";
import type { CaseSummary } from "@/lib/cases";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser, ROLE_LABELS } from "@/lib/server/user";
import type { Role } from "@/lib/server/user";
import type { EntityList } from "@/lib/entities";
import type { AuditEventPage } from "@/lib/reports";
import { ACTION_LABELS } from "@/lib/reports";
import type { DatasetFreshness, Screening, ScreeningList } from "@/lib/screening";
import { TONE_CLASSES, riskHeadline } from "@/lib/screening";

export const metadata: Metadata = { title: "Panel" };

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

/** Günün tek cümlesi: en acil konu önce. Sonuç vermeyen tarama hiçbir zaman temiz sayılmaz. */
function statusLine(input: {
  failed: number;
  overdue: number;
  pending: number;
  openCases: number;
}): { title: string; detail: string; href: string; action: string; calm: boolean } {
  if (input.overdue > 0) {
    return {
      title: `${input.overdue} vakanın süresi geçti.`,
      detail: "Süresi geçen vakalar önce ele alınmalı; her adım denetim izine yazılır.",
      href: "/cases?view=overdue",
      action: "Süresi geçenleri aç",
      calm: false,
    };
  }
  if (input.failed > 0) {
    return {
      title: `${input.failed} tarama sonuç vermedi.`,
      detail: "Bu müşteriler için sonuç YOK, temiz değil. Motor erişimi düzelince yeniden taranmalı.",
      href: "/screenings",
      action: "Taramaları aç",
      calm: false,
    };
  }
  if (input.pending > 0) {
    return {
      title: `${input.pending} eşleşme kararınızı bekliyor.`,
      detail: "Onaylamak ya da gerekçeyle elemek analistin kararıdır; her karar izde kalır.",
      href: "/screenings",
      action: "İncelemeye başla",
      calm: false,
    };
  }
  if (input.openCases > 0) {
    return {
      title: `${input.openCases} açık vaka var.`,
      detail: "Süresi geçen yok. Kapanış uyum görevlisinin onayıyla yapılır.",
      href: "/cases",
      action: "Vakaları aç",
      calm: true,
    };
  }
  return {
    title: "Karar bekleyen konu yok.",
    detail: "Yeni müşteri için tarama başlatabilirsiniz.",
    href: "/screenings",
    action: "Tarama başlat",
    calm: true,
  };
}

export default async function DashboardPage() {
  const user = await getCurrentUser();
  const canReadAudit = AUDIT_ROLES.includes(user.role);
  const [screenings, entities, freshness, audit, members, settings, cases] = await Promise.all([
    safeJson<ScreeningList>("/screenings?limit=100"),
    safeJson<EntityList>("/entities?limit=1"),
    safeJson<DatasetFreshness>("/screenings/datasets"),
    canReadAudit ? safeJson<AuditEventPage>("/audit/events?limit=6") : Promise.resolve(null),
    safeJson<Member[]>("/members"),
    safeJson<Setting[]>("/settings"),
    safeJson<{ summary: CaseSummary }>("/cases?status=open&limit=1"),
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
  const openCases = cases?.summary.open ?? 0;
  const overdue = cases?.summary.overdue ?? 0;
  const status = statusLine({ failed, overdue, pending, openCases });

  return (
    <div className="page space-y-6">
      <h1 className="page-title">Panel</h1>

      <section
        aria-label="Günün durumu"
        className="flex flex-col gap-4 rounded-card bg-ink p-5 text-ink-fg sm:flex-row sm:items-center sm:justify-between md:p-6"
      >
        <div className="flex min-w-0 gap-3.5">
          <ShieldAlert
            aria-hidden="true"
            strokeWidth={1.75}
            className={`mt-0.5 size-6 shrink-0 ${status.calm ? "text-ink-muted" : "text-seal"}`}
          />
          <div className="min-w-0">
            <p className="text-lg leading-snug font-semibold text-balance">{status.title}</p>
            <p className="mt-1 max-w-prose text-sm text-ink-muted">{status.detail}</p>
          </div>
        </div>
        <Link
          href={status.href}
          className="inline-flex min-h-10 shrink-0 items-center justify-center gap-1.5 rounded-md bg-seal px-4 text-sm font-semibold text-ink transition-opacity hover:opacity-90"
        >
          {status.action}
          <ArrowRight aria-hidden="true" className="size-4" />
        </Link>
      </section>

      {freshness?.any_stale === true && (
        <div
          role="status"
          className="rounded-card border border-warning/40 bg-warning-soft p-4 text-sm text-warning"
        >
          <strong className="font-semibold">Yaptırım verisi güncel değil.</strong>{" "}
          {freshness.datasets.length === 0
            ? "Veri kümesi senkronu henüz çalışmadı."
            : `Bazı listeler ${freshness.staleness_threshold_hours} saatten eski.`}{" "}
          Bu sürede alınan &ldquo;eşleşme yok&rdquo; sonuçları kesin kabul edilmemelidir.
        </div>
      )}

      <section aria-label="Özet" className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile
          label="İnceleme bekleyen"
          value={pending}
          hint={pending > 0 ? `${queue.length} taramada` : "Kuyruk boş"}
          tone={pending > 0 ? "warning" : "neutral"}
          href="/screenings"
        />
        <StatTile
          label="Onaylanmış eşleşme"
          value={confirmed}
          hint="Analistin doğruladığı"
          tone={confirmed > 0 ? "danger" : "neutral"}
          href="/screenings"
        />
        <StatTile
          label="Açık vaka"
          value={cases === null ? "—" : openCases}
          hint={overdue > 0 ? `${overdue} tanesinin süresi geçti` : "Süresi geçen yok"}
          tone={overdue > 0 ? "danger" : "neutral"}
          href="/cases"
        />
        <StatTile
          label="Kayıtlı varlık"
          value={entities?.total ?? "—"}
          hint="Şirket ve kişi"
          href="/entities"
        />
        <StatTile
          label="Tarama"
          value={screenings?.total ?? "—"}
          hint={failed > 0 ? `${failed} tanesi yapılamadı` : "Tümü tamamlandı"}
          tone={failed > 0 ? "danger" : "neutral"}
          href="/screenings"
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="min-w-0 space-y-6">
          <section className="panel">
            <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
              <h2 className="eyebrow">İnceleme kuyruğu</h2>
              <span className="font-mono text-xs text-muted">{queue.length}</span>
            </div>
            {queue.length === 0 ? (
              <p className="px-5 py-4 text-sm text-muted">
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
                    <li key={screening.id}>
                      <Link href={`/screenings/${screening.id}`} className="row-link px-5 py-3">
                        <div className={`rail rail-${headline.tone}`}>
                          <div className="truncate text-sm font-medium text-fg">{screening.subject_name}</div>
                          <div className="mt-0.5 text-xs text-muted">
                            {headline.text} · <span className="font-mono">{formatDate(screening.created_at)}</span>
                          </div>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {audit !== null && (
            <section className="panel">
              <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
                <h2 className="eyebrow">Son etkinlik</h2>
                <Link href="/audit" className="text-xs font-medium text-primary underline-offset-2 hover:underline">
                  Denetim izinin tamamı
                </Link>
              </div>
              {audit.items.length === 0 ? (
                <p className="px-5 py-4 text-sm text-muted">Henüz kayıtlı eylem yok.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {audit.items.map((event) => (
                    <li key={event.id} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
                      <span className="min-w-0 truncate text-fg">
                        {ACTION_LABELS[event.action] ?? event.action}
                        {event.actor_label !== null && (
                          <span className="text-muted"> · {event.actor_label}</span>
                        )}
                      </span>
                      <span className="shrink-0 font-mono text-xs text-muted">{formatDate(event.occurred_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>

        <div className="min-w-0 space-y-6">
          <section className="panel">
            <div className="border-b border-border px-5 py-3.5">
              <h2 className="eyebrow">Son taramalar</h2>
            </div>
            {items.length === 0 ? (
              <p className="px-5 py-4 text-sm text-muted">Henüz tarama yapılmadı.</p>
            ) : (
              <ul className="divide-y divide-border">
                {items.slice(0, 6).map((screening) => {
                  const headline = riskHeadline(screening);
                  return (
                    <li key={screening.id}>
                      <Link href={`/screenings/${screening.id}`} className="row-link px-5 py-3">
                        <span className="block truncate text-sm text-fg">{screening.subject_name}</span>
                        <span className="mt-1 flex flex-wrap items-center gap-2">
                          <span className={`rounded border px-1.5 py-0.5 text-xs ${TONE_CLASSES[headline.tone]}`}>
                            {headline.text}
                          </span>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="panel p-5">
            <h2 className="eyebrow mb-3">Ekip</h2>
            <ul className="divide-y divide-border">
              {(members ?? []).map((m) => (
                <li key={m.user_id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="min-w-0 truncate text-fg">{m.full_name ?? m.email}</span>
                  <span className="shrink-0 text-muted">{ROLE_LABELS[m.role as Role] ?? m.role}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="eyebrow">Kiracı ayarları</h2>
              <span className="text-xs text-muted">{canWriteSettings ? "Yazma yetkiniz var" : "Salt okunur"}</span>
            </div>
            {settings === null || settings.length === 0 ? (
              <p className="text-sm text-muted">Varsayılan eşikler ve saklama süreleri kullanılıyor.</p>
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
    </div>
  );
}
