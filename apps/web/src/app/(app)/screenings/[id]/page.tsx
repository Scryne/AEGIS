// Tarama detayı — adaylar, "neden eşleşti" kırılımı, kaynak referansı ve HITL kararı.

import Link from "next/link";
import { notFound } from "next/navigation";

import { MatchReview } from "@/components/match-review";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";
import type { MatchCandidate, ScreeningDetail } from "@/lib/screening";
import {
  BAND_LABELS,
  DECISION_LABELS,
  ROLE_LABELS,
  STATUS_LABELS,
  TONE_CLASSES,
  featureLabel,
  formatScore,
  formatThresholds,
  riskHeadline,
  schemaLabel,
  topicLabel,
} from "@/lib/screening";

export const metadata = { title: "Tarama sonucu" };

export const dynamic = "force-dynamic";

function formatDate(value: string | null): string {
  return value === null ? "—" : new Date(value).toLocaleString("tr-TR", { timeZone: "Europe/Istanbul" });
}

/** Skor ekseni: adayın skoru, eleme ve işaretleme sınırlarıyla birlikte (gerekçenin görsel özeti). */
function ScoreMeter({ score, thresholds }: { score: number; thresholds: Record<string, number> }) {
  const dismiss = thresholds.auto_dismiss_below;
  const flag = thresholds.auto_flag_at;
  const tone = flag !== undefined && score >= flag ? "bg-danger" : dismiss !== undefined && score < dismiss ? "bg-border-strong" : "bg-warning";
  return (
    <div className="relative mt-1.5 h-1.5 w-28 rounded-full bg-subtle" aria-hidden="true">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.min(Math.max(score, 0), 1) * 100}%` }} />
      {[dismiss, flag].map((t, i) =>
        t === undefined ? null : (
          <span key={i} className="absolute -top-0.5 h-2.5 w-px bg-fg/60" style={{ left: `${t * 100}%` }} />
        ),
      )}
    </div>
  );
}

function CandidateCard({
  candidate,
  screeningId,
  canDecide,
  thresholds,
}: {
  candidate: MatchCandidate;
  screeningId: string;
  canDecide: boolean;
  thresholds: Record<string, number>;
}) {
  const features = Object.entries(candidate.features).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const urgent = candidate.decision === "confirmed" || (candidate.decision === "pending" && candidate.flagged);
  const decisionTone = urgent
    ? "border-danger/40 bg-danger-soft text-danger"
    : candidate.decision === "dismissed"
      ? "border-border text-muted"
      : "border-warning/40 bg-warning-soft text-warning";
  const rail = urgent ? "border-l-danger" : candidate.decision === "pending" ? "border-l-warning" : "border-l-border-strong";

  return (
    <li className={`rounded-card border border-l-[3px] border-border bg-surface p-4 ${rail}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-fg">{candidate.caption}</div>
          <div className="mt-0.5 text-xs text-muted">
            {ROLE_LABELS[candidate.subject_role] ?? candidate.subject_role}: {candidate.subject_name} ·{" "}
            {schemaLabel(candidate.schema_type)}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {candidate.topics.map((topic) => (
              <span key={topic} className="rounded border border-danger/50 px-1.5 py-0.5 text-[11px] text-danger">
                {topicLabel(topic)}
              </span>
            ))}
            {candidate.datasets.map((dataset) => (
              <span
                key={dataset}
                className="rounded border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted"
              >
                {dataset}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end text-right">
          <div className="font-mono text-xl text-fg tabular-nums">{formatScore(candidate.score)}</div>
          <ScoreMeter score={candidate.score} thresholds={thresholds} />
          <div className="mt-1 text-[11px] text-muted">{BAND_LABELS[candidate.band]}</div>
          <span className={`mt-1 inline-block rounded-md border px-2 py-0.5 text-xs ${decisionTone}`}>
            {DECISION_LABELS[candidate.decision]}
          </span>
        </div>
      </div>

      {/* Şeffaflık: skorun neden bu olduğunu gösteren özellik kırılımı. */}
      {features.length > 0 && (
        <div className="mt-3 rounded-md bg-bg px-3 py-2">
          <div className="mb-1 text-[11px] font-semibold tracking-[0.07em] text-muted uppercase">Neden eşleşti</div>
          <ul className="space-y-1">
            {features.map(([name, weight]) => (
              <li key={name} className="flex items-center justify-between gap-3 text-xs" title={name}>
                <span className={weight < 0 ? "text-warning" : "text-fg"}>{featureLabel(name)}</span>
                <span className={`font-mono tabular-nums ${weight < 0 ? "text-warning" : "text-fg"}`}>
                  {weight > 0 ? "+" : ""}
                  {formatScore(weight)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        {candidate.source_url !== null ? (
          <a
            href={candidate.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex min-h-6 items-center font-medium text-primary underline-offset-2 hover:underline"
          >
            Kaynak kaydını aç ↗
          </a>
        ) : (
          <span>Kaynak bağlantısı yok</span>
        )}
        <span className="font-mono break-all">{candidate.external_id}</span>
      </div>

      {candidate.review_note !== null && (
        <p className="mt-2 text-xs text-muted">
          <span className="font-medium text-fg">Gerekçe:</span> {candidate.review_note}
          {candidate.decided_automatically && " (eşik bandı tarafından otomatik)"}
        </p>
      )}

      {canDecide &&
        (candidate.decision === "pending" ? (
          <MatchReview screeningId={screeningId} candidate={candidate} />
        ) : (
          <details className="group mt-3 border-t border-border pt-2">
            <summary className="inline-flex min-h-8 cursor-pointer list-none items-center text-xs font-medium text-primary">
              Kararı değiştir
              <span className="ml-1 transition-transform group-open:rotate-90" aria-hidden="true">
                ›
              </span>
            </summary>
            <MatchReview screeningId={screeningId} candidate={candidate} />
          </details>
        ))}
    </li>
  );
}

export default async function ScreeningDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const user = await getCurrentUser();
  const res = await serverFetch(`/screenings/${id}`);
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error("Tarama yüklenemedi.");
  const screening = (await res.json()) as ScreeningDetail;

  // Karar yetkisi: analist dosyayı hazırlar, kararı uyumdan sorumlu rol verir.
  const canDecide = user.role === "owner" || user.role === "compliance_officer";
  const headline = riskHeadline(screening);
  const pending = screening.candidates.filter((c) => c.decision === "pending");
  const decided = screening.candidates.filter((c) => c.decision !== "pending");
  const confirmed = screening.candidates.filter((c) => c.decision === "confirmed");

  return (
    <div className="page space-y-6">
      <div>
        <Link href="/screenings" className="back-link">
          ← Taramalar
        </Link>
        <h1 className="page-title mt-1">{screening.subject_name}</h1>
        <p className="text-sm text-muted">
          {formatDate(screening.created_at)} · {STATUS_LABELS[screening.status]}
          {screening.duration_ms !== null && ` · ${(screening.duration_ms / 1000).toLocaleString("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} sn`}
        </p>
      </div>

      <div className={`rounded-card border p-4 ${TONE_CLASSES[headline.tone]}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-base font-semibold">{headline.text}</div>
            {confirmed.length > 0 && (
              <p className="mt-1 text-sm text-fg">
                Onaylanan:{" "}
                {confirmed
                  .map((c) => `${c.caption}${c.topics.length ? ` (${[...new Set(c.topics.map(topicLabel))].join(", ")})` : ""}`)
                  .join("; ")}
              </p>
            )}
          </div>
          {screening.entity_id !== null && (
            <Link href={`/entities/${screening.entity_id}`} className="btn-quiet shrink-0">
              Varlık dosyası
            </Link>
          )}
        </div>
        {screening.status === "failed" && (
          <p className="mt-1 text-xs">
            Motor hatası: {screening.error}. Bu kayıt bir tarama sonucu DEĞİLDİR; veri
            kümesine erişilemediği için hiçbir liste kontrol edilememiştir. Lütfen tekrar
            deneyin.
          </p>
        )}
      </div>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Aday", screening.summary.total],
          ["Bekleyen", screening.summary.pending],
          ["Onaylı", screening.summary.confirmed],
          ["Elenen", screening.summary.dismissed],
        ].map(([label, value]) => (
          <div key={String(label)} className="panel p-3">
            <div className="text-xs text-muted">{label}</div>
            <div className="font-mono text-xl font-semibold text-fg tabular-nums">{value}</div>
          </div>
        ))}
      </section>

      <section className="panel p-5">
        <h2 className="mb-3 eyebrow">
          Taranan özneler
        </h2>
        <ul className="divide-y divide-border">
          {screening.subjects.map((subject) => (
            <li key={subject.key} className="py-2 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-fg">{subject.name}</span>
                <span className="text-xs text-muted">
                  {ROLE_LABELS[subject.role] ?? subject.role}
                </span>
              </div>
              <div className="font-mono text-xs text-muted">
                {subject.normalized}
                {subject.stripped.length > 0 && ` (atılan ek: ${subject.stripped.join(", ")})`}
              </div>
            </li>
          ))}
        </ul>
      </section>

      {pending.length > 0 && (
        <section className="space-y-3">
          <h2 className="eyebrow">
            İnceleme bekleyen eşleşmeler
          </h2>
          <ul className="space-y-3">
            {pending.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                screeningId={screening.id}
                canDecide={canDecide}
                thresholds={screening.thresholds}
              />
            ))}
          </ul>
        </section>
      )}

      {decided.length > 0 && (
        <section className="space-y-3">
          <h2 className="eyebrow">
            Karara bağlanmış eşleşmeler
          </h2>
          {/* Elenen adaylar da gösterilir: dosya raporu (E1.5) "gerekçesiyle elenen
              eşleşmeler"i içermek zorundadır. */}
          <ul className="space-y-3">
            {decided.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                screeningId={screening.id}
                canDecide={canDecide}
                thresholds={screening.thresholds}
              />
            ))}
          </ul>
        </section>
      )}

      <section className="panel p-5 text-xs text-muted">
        <h2 className="eyebrow mb-2">Koşu bilgisi</h2>
        <dl className="grid gap-1 sm:grid-cols-2">
          <div>
            <dt className="inline font-medium">Veri kümesi: </dt>
            <dd className="inline font-mono">{screening.dataset}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Algoritma: </dt>
            <dd className="inline font-mono">{screening.algorithm}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Eşikler: </dt>
            <dd className="inline break-words">{formatThresholds(screening.thresholds)}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Liste sürümleri: </dt>
            <dd className="inline font-mono break-all">
              {Object.entries(screening.dataset_versions)
                .map(([name, info]) => `${name}@${info.version ?? "?"}`)
                .join(", ") || "kayıtlı sürüm yok"}
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
