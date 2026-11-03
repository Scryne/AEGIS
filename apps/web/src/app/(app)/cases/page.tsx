// Vaka kuyruğu (E3.2): karar bekleyen her konu, son tarihe göre en acil üstte.
//
// Özet şerit rolün sorusunu cevaplar: ne açık, ne gecikti, bana ne düştü, kime atanmadı.
// Kritik izleme alarmı vakayı kendisi açar (EDD işaretli); elle vaka varlık sayfasından açılır.

import Link from "next/link";

import { serverFetch } from "@/lib/server/backend";
import {
  SEVERITY_TONE,
  SOURCE_LABELS,
  STATUS_TONE,
  dueText,
  memberLabel,
  type CaseRow,
  type CaseSummary,
  type Member,
} from "@/lib/cases";

export const metadata = { title: "Vakalar" };

export const dynamic = "force-dynamic";

const VIEWS = [
  { key: "open", label: "Açık", query: { status: "open" } },
  { key: "mine", label: "Bana atanan", query: { status: "open", mine: "true" } },
  { key: "overdue", label: "Süresi geçen", query: { status: "open", overdue: "true" } },
  { key: "decided", label: "Karara bağlanan", query: { status: "decided" } },
  { key: "all", label: "Tümü", query: { status: "all" } },
] as const;

type ViewKey = (typeof VIEWS)[number]["key"];

export default async function CasesPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const params = await searchParams;
  const view: ViewKey = VIEWS.some((v) => v.key === params.view) ? (params.view as ViewKey) : "open";
  const current = VIEWS.find((v) => v.key === view)!;
  const [res, membersRes] = await Promise.all([
    serverFetch(`/cases?${new URLSearchParams({ ...current.query, limit: "200" })}`),
    serverFetch("/members"),
  ]);
  const data = res.ok ? ((await res.json()) as { items: CaseRow[]; summary: CaseSummary }) : null;
  const members = membersRes.ok ? ((await membersRes.json()) as Member[]) : [];

  const tiles = data
    ? [
        { label: "Açık vaka", value: data.summary.open, href: "/cases?view=open", tone: "text-fg" },
        {
          label: "Süresi geçen",
          value: data.summary.overdue,
          href: "/cases?view=overdue",
          tone: data.summary.overdue > 0 ? "text-danger" : "text-fg",
        },
        { label: "Bana atanan", value: data.summary.mine, href: "/cases?view=mine", tone: "text-fg" },
        {
          label: "Atanmamış",
          value: data.summary.unassigned,
          href: "/cases?view=open",
          tone: data.summary.unassigned > 0 ? "text-warning" : "text-fg",
        },
        {
          label: "EDD süren",
          value: data.summary.edd_open,
          href: "/cases?view=open",
          tone: data.summary.edd_open > 0 ? "text-danger" : "text-fg",
        },
      ]
    : [];

  return (
    <div className="page space-y-6">
      <div>
        <h1 className="page-title">Vakalar</h1>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Karar gerektiren her konu bir vakadır. Yaptırım alarmı vakayı kendisi açar ve
          sıkılaştırılmış inceleme (EDD) listesini ekler; diğer vakalar varlık sayfasından açılır.
          Onay ve kapanış uyum uzmanınındır; her adım denetim izine yazılır.
        </p>
      </div>

      {data && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {tiles.map((t) => (
            <Link
              key={t.label}
              href={t.href}
              className="panel px-4 py-3 hover:border-primary"
            >
              <dt className="text-xs text-muted">{t.label}</dt>
              <dd className={`mt-1 font-mono text-2xl tabular-nums ${t.tone}`}>{t.value}</dd>
            </Link>
          ))}
        </dl>
      )}

      <nav aria-label="Vaka görünümü" className="flex gap-1 overflow-x-auto">
        {VIEWS.map((v) => (
          <Link
            key={v.key}
            href={`/cases?view=${v.key}`}
            aria-current={view === v.key ? "page" : undefined}
            className={`shrink-0 rounded-md px-3 py-1.5 text-sm whitespace-nowrap ${
              view === v.key ? "bg-surface font-medium text-primary shadow-sm" : "text-muted hover:text-fg"
            }`}
          >
            {v.label}
          </Link>
        ))}
      </nav>

      {data === null ? (
        <p role="alert" className="rounded-card border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
          Vakalar yüklenemedi. Sayfayı yenileyin; sorun sürerse API&apos;nin çalıştığını kontrol edin.
        </p>
      ) : data.items.length === 0 ? (
        <div className="panel p-8 text-center">
          <p className="text-sm font-medium text-fg">
            {view === "open" ? "Açık vaka yok." : "Bu görünümde vaka yok."}
          </p>
          <p className="mt-1 text-xs text-muted">
            İzleme kritik ya da yüksek dereceli bir fark bulduğunda vaka burada belirir.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border panel overflow-hidden">
          {data.items.map((c) => (
            <li key={c.id}>
              <Link
                href={`/cases/${c.id}`}
                className="grid gap-2 px-5 py-4 hover:bg-subtle sm:grid-cols-[1fr_auto] sm:items-center"
              >
                <div className="min-w-0 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full border px-2 py-0.5 text-xs font-medium ${SEVERITY_TONE[c.severity]}`}
                    >
                      {c.severity_label}
                    </span>
                    <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_TONE[c.status]}`}>
                      {c.status_label}
                    </span>
                    {c.edd && c.status !== "escalated" && (
                      <span className="rounded-full border border-danger px-2 py-0.5 text-xs text-danger">
                        EDD
                      </span>
                    )}
                  </div>
                  <p className="truncate text-sm font-medium text-fg">{c.title}</p>
                  <p className="truncate text-xs text-muted">
                    {c.entity_name ?? "(silinmiş kayıt)"} · {SOURCE_LABELS[c.source]} ·{" "}
                    {memberLabel(members, c.assignee_user_id)}
                  </p>
                </div>
                <div className="text-xs sm:text-right">
                  {c.status === "approved" || c.status === "closed" ? (
                    <span className="text-muted">
                      {c.status === "closed" ? "Kapandı" : "Onaylandı"}{" "}
                      {c.decided_at ? new Date(c.decided_at).toLocaleDateString("tr-TR") : ""}
                    </span>
                  ) : (
                    <span className={c.overdue ? "font-medium text-danger" : "text-muted"}>
                      {dueText(c.due_at)}
                    </span>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
