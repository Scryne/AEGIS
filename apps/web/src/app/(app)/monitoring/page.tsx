// İzleme alarmları (E2.4): izlenen varlıkların gece yeniden taramasında çıkan önemli farklar.
//
// Her alarm hangi kaydın neden değiştiğini düz Türkçe söyler ve iki koşuya (önceki/yeni)
// bağlanır. Görülen alarm silinmez, gerekçesiyle "görüldü" olur.

import { MonitoringPreferences, type NotificationPrefs } from "@/components/monitoring-preferences";
import Link from "next/link";

import { MonitoringAck } from "@/components/monitoring-ack";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";

export const metadata = { title: "İzleme" };

interface MonitoringRun {
  id: string;
  started_at: string;
  duration_ms: number;
  checked: number;
  alerts: number;
  failed: number;
  failures: { entity_id: string; entity_name: string; reason: string }[];
}

export const dynamic = "force-dynamic";

interface AlertItem {
  kind: "new_match" | "removed_confirmed" | "topics_changed";
  subject_name: string;
  external_id: string;
  caption: string;
  detail: string;
}

interface Alert {
  id: string;
  entity_id: string;
  entity_name: string | null;
  screening_id: string;
  previous_screening_id: string | null;
  items: AlertItem[];
  status: "open" | "acknowledged";
  severity: "critical" | "high" | "info";
  severity_label: string;
  reassessment: {
    score_before: number | null;
    score_after: number;
    band_before: string | null;
    band_after: string;
    recorded_new: boolean;
  } | null;
  case_id: string | null;
  created_at: string;
  acknowledged_at: string | null;
  acknowledge_note: string | null;
}

const KIND_LABELS: Record<AlertItem["kind"], string> = {
  new_match: "Yeni eşleşme",
  removed_confirmed: "Onaylı eşleşme listeden çıktı",
  topics_changed: "Liste kaydı değişti",
};

const SEVERITY_TONE: Record<Alert["severity"], string> = {
  critical: "border-danger/40 bg-danger-soft text-danger",
  high: "border-warning/40 bg-warning-soft text-warning",
  info: "border-border text-muted",
};

const KIND_TONE: Record<AlertItem["kind"], string> = {
  new_match: "border-danger/40 bg-danger-soft text-danger",
  removed_confirmed: "border-warning/40 bg-warning-soft text-warning",
  topics_changed: "border-warning/40 bg-warning-soft text-warning",
};

export default async function MonitoringPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const user = await getCurrentUser();
  const params = await searchParams;
  const status = params.status === "acknowledged" ? "acknowledged" : params.status === "all" ? "" : "open";
  const query = new URLSearchParams({ limit: "100" });
  if (status) query.set("status", status);
  const [res, runsRes, prefsRes] = await Promise.all([
    serverFetch(`/monitoring/alerts?${query}`),
    serverFetch("/monitoring/runs?limit=1"),
    serverFetch("/monitoring/notifications"),
  ]);
  const data = res.ok ? ((await res.json()) as { items: Alert[]; open_count: number }) : null;
  const lastRun = runsRes.ok ? ((await runsRes.json()) as { items: MonitoringRun[] }).items[0] : undefined;
  const prefs = prefsRes.ok ? ((await prefsRes.json()) as NotificationPrefs) : null;
  const canEditPrefs = user.role === "owner" || user.role === "compliance_officer";
  const canAck = user.role !== "auditor";

  const tabs = [
    { key: "open", label: `Açık${data ? ` (${data.open_count})` : ""}` },
    { key: "acknowledged", label: "Görülen" },
    { key: "all", label: "Tümü" },
  ];
  const current = status || "all";

  return (
    <div className="page space-y-6">
      <div>
        <h1 className="page-title">İzleme</h1>
        <p className="mt-1 max-w-prose text-sm text-muted">
          İzlemeye alınan varlıklar her gece yaptırım verisi güncellendikten sonra yeniden taranır.
          Önceki koşuya göre yeni bir eşleşme, onaylı bir eşleşmenin listeden çıkması ya da liste
          kaydının değişmesi burada alarm olarak görünür. Her alarmda risk puanı yeniden kayda geçer;
          kritik ve yüksek dereceli alarm bir vaka açar (yaptırımda EDD listesiyle). İzlemeyi varlık
          sayfasından açarsınız.
        </p>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)] xl:grid-cols-[minmax(0,5fr)_minmax(0,2fr)]">
      <div className="min-w-0 space-y-6">
      {lastRun && lastRun.failed > 0 && (
        <div role="alert" className="rounded-card border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
          <strong className="font-semibold">{lastRun.failed} varlık son koşuda taranamadı.</strong>{" "}
          Bu varlıklar için sonuç YOK, temiz değil. Sonraki koşu yeniden dener.
          <ul className="mt-2 space-y-0.5">
            {lastRun.failures.slice(0, 5).map((f) => (
              <li key={f.entity_id}>
                <Link href={`/entities/${f.entity_id}`} className="underline underline-offset-2">
                  {f.entity_name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      <nav aria-label="Alarm durumu" className="flex gap-1">
        {tabs.map((tab) => (
          <Link
            key={tab.key}
            href={`/monitoring?status=${tab.key}`}
            aria-current={current === tab.key ? "page" : undefined}
            className={`rounded-md px-3 py-1.5 text-sm ${
              current === tab.key ? "bg-surface font-medium text-primary shadow-sm" : "text-muted hover:text-fg"
            }`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      {data === null ? (
        <p className="rounded-card border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
          Alarmlar yüklenemedi. Sayfayı yenileyin; sorun sürerse API'nin çalıştığını kontrol edin.
        </p>
      ) : data.items.length === 0 ? (
        <div className="panel p-8 text-center">
          <p className="text-sm font-medium text-fg">
            {current === "open" ? "Açık alarm yok." : "Bu görünümde alarm yok."}
          </p>
          <p className="mt-1 text-xs text-muted">
            Gece koşusu önemli bir fark bulduğunda alarm burada belirir.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {data.items.map((alert) => (
            <li key={alert.id} className="space-y-3 panel p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${SEVERITY_TONE[alert.severity]}`}>
                    {alert.severity_label}
                  </span>
                  <Link href={`/entities/${alert.entity_id}`} className="text-base font-medium text-fg underline">
                    {alert.entity_name ?? "(silinmiş kayıt)"}
                  </Link>
                </div>
                <span className="text-xs text-muted">{new Date(alert.created_at).toLocaleString("tr-TR")}</span>
              </div>
              <ul className="space-y-2">
                {alert.items.map((item) => (
                  <li key={`${item.kind}-${item.external_id}`} className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-3">
                    <span className={`w-fit shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium ${KIND_TONE[item.kind]}`}>
                      {KIND_LABELS[item.kind]}
                    </span>
                    <div className="min-w-0 text-sm">
                      <span className="text-fg">{item.caption}</span>{" "}
                      <span className="text-xs text-muted">· {item.subject_name} · {item.detail}</span>
                    </div>
                  </li>
                ))}
              </ul>
              {alert.reassessment && (
                <p className="text-xs text-muted">
                  Risk puanı:{" "}
                  <span className="font-mono text-fg tabular-nums">
                    {alert.reassessment.score_before ?? "—"} → {alert.reassessment.score_after}
                  </span>
                  {alert.reassessment.score_before === null
                    ? " (ilk kayıt)"
                    : alert.reassessment.score_before === alert.reassessment.score_after &&
                      " (onaylanmamış eşleşme puanı değiştirmez; karar vakada verilir)"}
                </p>
              )}
              <div className="flex flex-wrap gap-3 text-xs">
                {alert.case_id && (
                  <Link href={`/cases/${alert.case_id}`} className="font-medium text-primary underline">
                    Vakayı aç
                  </Link>
                )}
                <Link href={`/screenings/${alert.screening_id}`} className="text-primary underline">
                  Yeni koşuyu aç
                </Link>
                {alert.previous_screening_id && (
                  <Link href={`/screenings/${alert.previous_screening_id}`} className="text-muted underline">
                    Önceki koşu
                  </Link>
                )}
              </div>
              {alert.status === "acknowledged" ? (
                <p className="text-xs text-muted">
                  Görüldü · {alert.acknowledged_at ? new Date(alert.acknowledged_at).toLocaleString("tr-TR") : ""} ·{" "}
                  {alert.acknowledge_note}
                </p>
              ) : (
                canAck && <MonitoringAck alertId={alert.id} />
              )}
            </li>
          ))}
        </ul>
      )}
      </div>
      <aside className="min-w-0 space-y-6">
        <section className="panel p-5">
          <h2 className="eyebrow mb-3">Son koşu</h2>
          {lastRun ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div className="col-span-2">
                <dt className="text-xs text-muted">Zaman</dt>
                <dd className="font-mono text-fg">
                  {new Date(lastRun.started_at).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" })}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Taranan</dt>
                <dd className="font-mono text-fg">{lastRun.checked}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Alarm</dt>
                <dd className="font-mono text-fg">{lastRun.alerts}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Taranamayan</dt>
                <dd className={`font-mono ${lastRun.failed > 0 ? "text-danger" : "text-fg"}`}>{lastRun.failed}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Süre</dt>
                <dd className="font-mono text-fg">{(lastRun.duration_ms / 1000).toFixed(1)} sn</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted">Henüz koşu yok. İlk gece koşusundan sonra burada görünür.</p>
          )}
        </section>
        {prefs && <MonitoringPreferences initial={prefs} canEdit={canEditPrefs} />}
      </aside>
      </div>
    </div>
  );
}
