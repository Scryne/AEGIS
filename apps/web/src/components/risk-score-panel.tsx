"use client";

// Açıklanabilir risk puanı (E2.3). Puan tek başına bir sayı değil, faktör tablosudur:
// her satır ne kadar puan kattığını, gerekçesini ve dayandığı kaydı gösterir. Seviye (ADR-0008)
// "neden bu kademe", puan "ne kadar ve hangi faktörlerden" sorusunu cevaplar.

import { useRouter } from "next/navigation";
import { useState } from "react";

export interface ScoreFactor {
  code: string;
  label: string;
  points: number;
  occurrences: number;
  reason: string;
  evidence: string[];
}

export interface ScoreHistoryItem {
  id: string;
  score: number;
  band: string;
  band_label: string;
  reason: string;
  weights_version: string;
  created_at: string;
}

export interface RiskScore {
  entity_id: string;
  score: number;
  band: "low" | "medium" | "high";
  band_label: string;
  complete: boolean;
  weights_version: string;
  notes: string[];
  factors: ScoreFactor[];
  recorded: boolean;
  history: ScoreHistoryItem[];
}

const BAND_TONE: Record<RiskScore["band"], { text: string; bar: string; border: string }> = {
  low: { text: "text-success", bar: "bg-success", border: "border-success" },
  medium: { text: "text-warning", bar: "bg-warning", border: "border-warning" },
  high: { text: "text-danger", bar: "bg-danger", border: "border-danger" },
};

const REASON_LABELS: Record<string, string> = {
  manual: "elle kayda geçirildi",
  ubo_compute: "UBO hesabından sonra",
  monitoring_alert: "izleme alarmıyla otomatik",
  case_decision: "vaka kararıyla",
};

function Evidence({ refValue }: { refValue: string }) {
  if (/^https?:\/\//.test(refValue)) {
    return (
      <a href={refValue} target="_blank" rel="noreferrer" className="underline">
        kaynak
      </a>
    );
  }
  const [kind, id] = refValue.split(":", 2);
  if (kind === "ubo") return <a href="#ubo-baslik" className="underline">UBO hesabı</a>;
  if (kind === "entity" && id) return <a href={`/entities/${id}`} className="underline">varlık kaydı</a>;
  if (kind === "screening" && id) return <a href={`/screenings/${id}`} className="underline">tarama</a>;
  return <span className="font-mono">{refValue}</span>;
}

export function RiskScorePanel({ score, canWrite }: { score: RiskScore; canWrite: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tone = BAND_TONE[score.band];
  const max = Math.max(1, ...score.factors.map((f) => f.points));

  async function record() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/reports/score/${score.entity_id}/snapshot`, { method: "POST" });
      if (!res.ok) {
        const payload = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
        setError(payload?.error?.message ?? "Puan kayda geçirilemedi.");
        return;
      }
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4 panel p-5" aria-labelledby="puan-baslik">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id="puan-baslik" className="eyebrow">
            Risk puanı
          </h2>
          <p className="mt-1 max-w-prose text-xs text-muted">
            Yalnız yapılandırılmış bulgulardan hesaplanır (ağırlıklar {score.weights_version}); her
            satır gerekçesini ve dayandığı kaydı gösterir.
          </p>
        </div>
        <div className={`flex items-baseline gap-2 rounded-card border px-4 py-2 ${tone.border}`}>
          <span className={`text-4xl font-semibold tabular-nums ${tone.text}`}>{score.score}</span>
          <span className="text-xs text-muted">/ 100</span>
          <span className={`ml-2 text-sm font-medium ${tone.text}`}>{score.band_label}</span>
        </div>
      </div>

      {!score.complete && (
        <p className="text-xs text-warning">
          Dosyada karar bekleyen bulgular var; puan tamamlanmış değerlendirme sayılmaz.
        </p>
      )}
      {score.notes.map((note) => (
        <p key={note} className="text-xs text-danger">
          {note}
        </p>
      ))}

      {score.factors.length === 0 ? (
        <p className="text-sm text-muted">Puanı yükselten bir faktör yok.</p>
      ) : (
        <ul className="divide-y divide-border">
          {score.factors.map((factor) => (
            <li key={factor.code} className="grid gap-1 py-2 sm:grid-cols-[12rem_1fr_3rem] sm:items-center sm:gap-3">
              <div className="text-sm text-fg">
                {factor.label}
                {factor.occurrences > 1 && <span className="text-xs text-muted"> ×{factor.occurrences}</span>}
              </div>
              <div className="min-w-0 space-y-1">
                <div className="h-1.5 w-full rounded-full bg-border" aria-hidden="true">
                  <div className={`h-1.5 rounded-full ${tone.bar}`} style={{ width: `${(factor.points / max) * 100}%` }} />
                </div>
                <p className="text-xs text-muted">{factor.reason}</p>
                {factor.evidence.length > 0 && (
                  <p className="flex flex-wrap gap-x-2 text-xs text-muted">
                    Dayanak:
                    {factor.evidence.slice(0, 4).map((ref) => (
                      <Evidence key={ref} refValue={ref} />
                    ))}
                  </p>
                )}
              </div>
              <div className="text-right font-mono text-sm tabular-nums text-fg">+{factor.points}</div>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
        <div className="text-xs text-muted">
          {score.recorded
            ? "Bu döküm kayda geçmiş durumda."
            : "Canlı döküm son kayıttan farklı (ya da hiç kaydedilmedi)."}
        </div>
        {canWrite && !score.recorded && (
          <button
            type="button"
            onClick={record}
            disabled={busy}
            className="btn-quiet hover:border-primary disabled:opacity-60"
          >
            {busy ? "Kaydediliyor…" : "Puanı kayda geçir"}
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {score.history.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Zaman çizelgesi</h3>
          <ol className="space-y-1">
            {score.history.map((item) => (
              <li key={item.id} className="grid grid-cols-[2rem_3.5rem_1fr] items-baseline gap-x-2 text-xs">
                <span className="text-right font-mono tabular-nums text-fg">{item.score}</span>
                <span className="text-fg">{item.band_label}</span>
                <span className="text-muted">
                  {new Date(item.created_at).toLocaleString("tr-TR")} · {REASON_LABELS[item.reason] ?? item.reason}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
