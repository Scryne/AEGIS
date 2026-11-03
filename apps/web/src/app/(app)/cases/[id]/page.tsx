// Vaka ayrıntısı (E3.2): önce sonuç (derece, durum, son tarih), sonra yapılacaklar (eylemler,
// EDD listesi), en altta kanıt (yorumlar, denetim izinden tam geçmiş). Denetçi her şeyi görür,
// hiçbir düğmeyi görmez.

import Link from "next/link";
import { notFound } from "next/navigation";

import { CaseActions, CaseAssign, CaseCommentForm, EddChecklist } from "@/components/case-controls";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser, ROLE_LABELS, type Role } from "@/lib/server/user";
import {
  HISTORY_LABELS,
  SEVERITY_TONE,
  SOURCE_LABELS,
  STATUS_TONE,
  dueText,
  formatDateTime,
  memberLabel,
  type CaseDetail,
  type CaseHistoryEvent,
  type Member,
} from "@/lib/cases";

export const dynamic = "force-dynamic";

const STATUS_NAMES: Record<string, string> = {
  new: "Yeni",
  in_review: "İncelemede",
  escalated: "EDD",
  approved: "Onaylandı",
  closed: "Kapandı",
};

function actorText(e: CaseHistoryEvent, members: Member[]): string {
  if (e.actor_role === "monitoring") return "İzleme (otomatik)";
  const who = memberLabel(members, e.actor_user_id);
  const role = e.actor_role && e.actor_role in ROLE_LABELS ? ROLE_LABELS[e.actor_role as Role] : e.actor_role;
  return role ? `${who} · ${role}` : who;
}

function eventText(e: CaseHistoryEvent, detail: CaseDetail, members: Member[]): string {
  const p = e.payload;
  switch (e.action) {
    case "case.open":
      return `${SOURCE_LABELS[(p.source as CaseDetail["source"]) ?? "manual"] ?? p.source}${p.edd ? " · EDD listesiyle" : ""}`;
    case "case.transition": {
      const from = STATUS_NAMES[String(p.from)] ?? p.from;
      const to = STATUS_NAMES[String(p.to)] ?? p.to;
      return `${from} → ${to}${p.reason ? ` · ${p.reason}` : ""}${p.risk_score_snapshot_id ? " · risk puanı yeniden kayda geçti" : ""}`;
    }
    case "case.assign":
      return `${memberLabel(members, (p.to as string) ?? null)}`;
    case "case.due":
      return p.to ? new Date(String(p.to)).toLocaleDateString("tr-TR") : "—";
    case "case.edd_item": {
      const label = detail.edd_checklist?.find((i) => i.key === p.key)?.label ?? String(p.key);
      return `${p.done ? "Tamamlandı" : "Geri alındı"}: ${label}${p.note ? ` · ${p.note}` : ""}`;
    }
    case "case.comment":
      return "Yorum eklendi";
    default:
      return "";
  }
}

export default async function CaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const user = await getCurrentUser();
  const [res, membersRes] = await Promise.all([serverFetch(`/cases/${id}`), serverFetch("/members")]);
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error("Vaka yüklenemedi.");
  const c = (await res.json()) as CaseDetail;
  const members = membersRes.ok ? ((await membersRes.json()) as Member[]) : [];

  const canWrite = user.role !== "auditor";
  const canDecide = user.role === "owner" || user.role === "compliance_officer";
  const isOpen = c.status === "new" || c.status === "in_review" || c.status === "escalated";
  const eddDone = c.edd_checklist?.filter((i) => i.done).length ?? 0;
  const eddTotal = c.edd_checklist?.length ?? 0;

  return (
    <div className="page space-y-6">
      <div className="space-y-2">
        <Link href="/cases" className="text-xs text-muted underline">
          ← Vakalar
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${SEVERITY_TONE[c.severity]}`}>
            {c.severity_label}
          </span>
          <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_TONE[c.status]}`}>{c.status_label}</span>
          {c.edd && (
            <span className="rounded-full border border-danger px-2 py-0.5 text-xs text-danger">
              EDD · {eddDone}/{eddTotal}
            </span>
          )}
        </div>
        <h1 className="page-title text-balance">{c.title}</h1>
        <p className="text-sm text-muted">
          <Link href={`/entities/${c.entity_id}`} className="text-fg underline">
            {c.entity_name ?? "(silinmiş kayıt)"}
          </Link>{" "}
          · {SOURCE_LABELS[c.source]}
          {c.source_screening_id && (
            <>
              {" · "}
              <Link href={`/screenings/${c.source_screening_id}`} className="text-primary underline">
                Kaynak tarama
              </Link>
            </>
          )}
          {c.source_alert_id && (
            <>
              {" · "}
              <Link href="/monitoring?status=all" className="text-primary underline">
                İzleme alarmı
              </Link>
            </>
          )}
        </p>
      </div>

      <section aria-labelledby="durum-baslik" className="space-y-4 panel p-5">
        <h2 id="durum-baslik" className="sr-only">
          Durum ve sorumluluk
        </h2>
        <dl className="grid gap-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted">Son tarih</dt>
            <dd className={c.overdue ? "font-medium text-danger" : "text-fg"}>
              {isOpen ? dueText(c.due_at) : "—"}
              <span className="block text-xs text-muted">{formatDateTime(c.due_at)}</span>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Açıldı</dt>
            <dd className="text-fg">{formatDateTime(c.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">İlk inceleme</dt>
            <dd className="text-fg">{formatDateTime(c.first_review_at)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Karar</dt>
            <dd className="text-fg">{formatDateTime(c.decided_at)}</dd>
          </div>
        </dl>
        {canWrite && isOpen ? (
          <div className="border-t border-border pt-4">
            <CaseAssign
              caseId={c.id}
              assignee={c.assignee_user_id}
              members={members}
              canDue={canDecide}
              dueAt={c.due_at}
            />
          </div>
        ) : (
          <p className="border-t border-border pt-4 text-sm text-muted">
            Atanan: <span className="text-fg">{memberLabel(members, c.assignee_user_id)}</span>
          </p>
        )}
        {c.resolution && (
          <div className="border-t border-border pt-4">
            <p className="text-xs text-muted">Karar gerekçesi</p>
            <p className="mt-1 text-sm whitespace-pre-line text-fg">{c.resolution}</p>
          </div>
        )}
      </section>

      {canWrite && (
        <section aria-labelledby="eylem-baslik" className="space-y-3 panel p-5">
          <h2 id="eylem-baslik" className="eyebrow">
            Sıradaki adım
          </h2>
          <CaseActions caseId={c.id} actions={c.allowed_actions} eddOpen={c.edd && !c.edd_complete} />
          {!canDecide && (
            <p className="text-xs text-muted">Onay ve kapanış uyum uzmanınındır; siz inceleyip yükseltebilirsiniz.</p>
          )}
        </section>
      )}

      {c.edd && c.edd_checklist && (
        <section aria-labelledby="edd-baslik" className="panel p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="edd-baslik" className="eyebrow">
              Sıkılaştırılmış inceleme listesi
            </h2>
            <span className="font-mono text-xs text-muted tabular-nums">
              {eddDone}/{eddTotal} · {c.edd_template_version}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">
            Genel bir şablondur (FATF Tavsiye 10/12 başlıkları); kurumunuzun politikasına göre uygulayın.
            Her madde ne yapıldığı yazılarak tamamlanır.
          </p>
          <EddChecklist caseId={c.id} items={c.edd_checklist} editable={canWrite && isOpen} />
        </section>
      )}

      <section aria-labelledby="yorum-baslik" className="space-y-3 panel p-5">
        <h2 id="yorum-baslik" className="eyebrow">
          Yorumlar
        </h2>
        {c.comments.length === 0 ? (
          <p className="text-sm text-muted">Henüz yorum yok.</p>
        ) : (
          <ul className="space-y-3">
            {c.comments.map((m) => (
              <li key={m.id} className="rounded-md border border-border bg-bg p-3">
                <p className="text-sm whitespace-pre-line text-fg">{m.body}</p>
                <p className="mt-1 text-xs text-muted">
                  {memberLabel(members, m.author_user_id)} · {formatDateTime(m.created_at)}
                </p>
              </li>
            ))}
          </ul>
        )}
        {canWrite && <CaseCommentForm caseId={c.id} />}
      </section>

      <section aria-labelledby="gecmis-baslik" className="panel p-5">
        <h2 id="gecmis-baslik" className="eyebrow">
          Geçmiş
        </h2>
        <p className="mt-1 text-xs text-muted">Değiştirilemez denetim izinden okunur.</p>
        <ol className="mt-3 space-y-3 border-l border-border pl-4">
          {c.history.map((e) => (
            <li key={e.seq} className="relative">
              <span aria-hidden="true" className="absolute top-1.5 -left-[1.3rem] size-2 rounded-full bg-border" />
              <p className="text-sm text-fg">
                <span className="font-medium">{HISTORY_LABELS[e.action] ?? e.action}</span>
                {eventText(e, c, members) && <span className="text-muted"> · {eventText(e, c, members)}</span>}
              </p>
              <p className="text-xs text-muted">
                {formatDateTime(e.occurred_at)} · {actorText(e, members)} ·{" "}
                <span className="font-mono">#{e.seq}</span>
              </p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
