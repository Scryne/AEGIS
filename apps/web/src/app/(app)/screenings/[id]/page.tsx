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
  riskHeadline,
  topicLabel,
} from "@/lib/screening";

export const dynamic = "force-dynamic";

function formatDate(value: string | null): string {
  return value === null ? "—" : new Date(value).toLocaleString("tr-TR");
}

function CandidateCard({
  candidate,
  screeningId,
  canDecide,
}: {
  candidate: MatchCandidate;
  screeningId: string;
  canDecide: boolean;
}) {
  const features = Object.entries(candidate.features).sort((a, b) => b[1] - a[1]);
  const decisionTone =
    candidate.decision === "confirmed"
      ? "border-danger text-danger"
      : candidate.decision === "dismissed"
        ? "border-border text-muted"
        : candidate.flagged
          ? "border-danger text-danger"
          : "border-warning text-warning";

  return (
    <li className="rounded-card border border-border bg-bg p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-sm font-medium text-fg">{candidate.caption}</div>
          <div className="mt-0.5 text-xs text-muted">
            {ROLE_LABELS[candidate.subject_role] ?? candidate.subject_role}:{" "}
            {candidate.subject_name} · {candidate.schema_type}
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {candidate.topics.map((topic) => (
              <span
                key={topic}
                className="rounded border border-danger px-1.5 py-0.5 text-[10px] text-danger"
              >
                {topicLabel(topic)}
              </span>
            ))}
            {candidate.datasets.map((dataset) => (
              <span
                key={dataset}
                className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted"
              >
                {dataset}
              </span>
            ))}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-lg text-fg">{candidate.score.toFixed(2)}</div>
          <div className="text-[10px] text-muted">{BAND_LABELS[candidate.band]}</div>
          <span className={`mt-1 inline-block rounded-md border px-2 py-0.5 text-xs ${decisionTone}`}>
            {DECISION_LABELS[candidate.decision]}
          </span>
        </div>
      </div>

      {/* Şeffaflık: skorun neden bu olduğunu gösteren özellik kırılımı. */}
      {features.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] font-medium tracking-wide text-muted uppercase">
            Neden eşleşti
          </div>
          <ul className="space-y-0.5">
            {features.map(([name, weight]) => (
              <li key={name} className="flex justify-between font-mono text-xs text-muted">
                <span>{name}</span>
                <span className={weight < 0 ? "text-warning" : "text-fg"}>{weight.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted">
        {candidate.source_url !== null && (
          <a
            href={candidate.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="underline hover:text-fg"
          >
            Kaynak kaydı
          </a>
        )}
        <span className="font-mono">{candidate.external_id}</span>
      </div>

      {candidate.review_note !== null && (
        <p className="mt-2 text-xs text-muted">
          <span className="font-medium">Gerekçe:</span> {candidate.review_note}
          {candidate.decided_automatically && " (eşik bandı tarafından otomatik)"}
        </p>
      )}

      {canDecide && <MatchReview screeningId={screeningId} candidate={candidate} />}
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

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <Link href="/screenings" className="text-xs text-muted hover:text-fg">
          ← Taramalar
        </Link>
        <h1 className="mt-1 text-2xl font-semibold text-fg">{screening.subject_name}</h1>
        <p className="text-sm text-muted">
          {formatDate(screening.created_at)} · {STATUS_LABELS[screening.status]}
          {screening.duration_ms !== null && ` · ${(screening.duration_ms / 1000).toFixed(1)} sn`}
        </p>
      </div>

      <div className={`rounded-card border p-4 ${TONE_CLASSES[headline.tone]}`}>
        <div className="text-sm font-semibold">{headline.text}</div>
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
          <div key={String(label)} className="rounded-card border border-border bg-surface p-3">
            <div className="text-xs text-muted">{label}</div>
            <div className="text-xl font-semibold text-fg">{value}</div>
          </div>
        ))}
      </section>

      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">
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
          <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">
            İnceleme bekleyen eşleşmeler
          </h2>
          <ul className="space-y-3">
            {pending.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                screeningId={screening.id}
                canDecide={canDecide}
              />
            ))}
          </ul>
        </section>
      )}

      {decided.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">
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
              />
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-card border border-border bg-surface p-5 text-xs text-muted">
        <h2 className="mb-2 text-sm font-semibold tracking-wide uppercase">Koşu bilgisi</h2>
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
            <dd className="inline font-mono">{JSON.stringify(screening.thresholds)}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Liste sürümleri: </dt>
            <dd className="inline font-mono">
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
