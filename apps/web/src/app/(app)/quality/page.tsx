// Eşleşme kalitesi (E3.6): insan kararlarından yanlış pozitif ve inceleme oranı, işaretleme
// isabeti, eşik taraması ve önerisi, olumsuz haber isabeti, haftalık eğilim. Eşiği bu sayfa
// değiştirmez; öneri uyum uzmanının kararıdır.

import { QualitySnapshotButton } from "@/components/quality-snapshot";
import { QualitySweep } from "@/components/quality-sweep";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";

export const dynamic = "force-dynamic";

interface Matching {
  total: number;
  auto_dismissed: number;
  pending: number;
  confirmed: number;
  dismissed: number;
  false_positive_rate: number | null;
  review_rate: number | null;
  flag_precision: number | null;
  flag_recall: number | null;
  min_confirmed_score: number | null;
  sweep: { threshold: number; saved_reviews: number; lost_confirmed: number; current: boolean }[];
  recommendation: { status: "insufficient" | "keep" | "raise"; message: string; threshold?: number } | null;
}

interface Quality {
  thresholds: { auto_dismiss_below: number; auto_flag_at: number };
  matching: Matching;
  adverse_media: {
    candidates: number;
    reviewed: number;
    relevant: number;
    precision: number | null;
    hint_precision: number | null;
    promotion_ready: boolean;
  };
  history: {
    id: string;
    created_at: string;
    reason: string;
    label_count: number;
    thresholds: { auto_dismiss_below: number };
    metrics: { false_positive_rate: number | null; review_rate: number | null };
  }[];
}

const pct = (v: number | null | undefined) => (v == null ? "—" : `%${(v * 100).toLocaleString("tr-TR", { maximumFractionDigits: 1 })}`);
const REASON: Record<string, string> = { manual: "Elle", weekly: "Haftalık" };

export default async function QualityPage() {
  const user = await getCurrentUser();
  if (user.role === "analyst") {
    return (
      <div className="mx-auto max-w-4xl">
        <h1 className="text-2xl font-semibold text-fg">Eşleşme kalitesi</h1>
        <p className="mt-2 text-sm text-muted">Bu sayfa sahip, uyum uzmanı ve denetçiye açıktır.</p>
      </div>
    );
  }
  const res = await serverFetch("/quality/matching");
  if (!res.ok) throw new Error("Kalite ölçümü yüklenemedi.");
  const q = (await res.json()) as Quality;
  const m = q.matching;
  const canWrite = user.role === "owner" || user.role === "compliance_officer";
  const rec = m.recommendation;

  const tiles: [string, string, string][] = [
    ["Yanlış pozitif oranı", pct(m.false_positive_rate), "İnsanın elediği / karar verdiği"],
    ["İnceleme oranı", pct(m.review_rate), "İnsan kararı gereken aday payı"],
    ["İşaret isabeti", pct(m.flag_precision), `Skor ≥ ${q.thresholds.auto_flag_at} olup onaylanan`],
    ["İşaret duyarlılığı", pct(m.flag_recall), "Onaylananların işaretlenmiş payı"],
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-fg">Eşleşme kalitesi</h1>
          <p className="mt-1 max-w-prose text-sm text-muted">
            Ölçüm, analistlerinizin eşleşme kararlarından çıkar: onaylanan gerçek eşleşme, elenen yanlış
            pozitiftir. Motorun kendiliğinden elediği adayların doğrusu bilinmez, ölçüme girmez. Her yeni karar
            bir sonraki ölçümü besler.
          </p>
        </div>
        {canWrite && <QualitySnapshotButton />}
      </div>

      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map(([label, value, hint]) => (
          <div key={label} className="rounded-card border border-border bg-surface px-4 py-3">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="mt-1 font-mono text-2xl text-fg tabular-nums">{value}</dd>
            <dd className="mt-0.5 text-xs text-muted">{hint}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-muted">
        Etiket: <span className="font-mono">{m.confirmed}</span> onaylı, <span className="font-mono">{m.dismissed}</span>{" "}
        elenen · bekleyen <span className="font-mono">{m.pending}</span> · motorun elediği{" "}
        <span className="font-mono">{m.auto_dismissed}</span> · toplam aday <span className="font-mono">{m.total}</span>
      </p>

      <section aria-labelledby="esik-baslik" className="space-y-4 rounded-card border border-border bg-surface p-5">
        <div>
          <h2 id="esik-baslik" className="text-sm font-semibold tracking-wide text-muted uppercase">
            Otomatik eleme eşiği
          </h2>
          <p className="mt-1 text-xs text-muted">
            Mevcut: <span className="font-mono">{q.thresholds.auto_dismiss_below}</span>. Eşik yükseldikçe daha az
            inceleme gerekir; onaylı bir eşleşmenin altında kalması kabul edilemez.
          </p>
        </div>
        {rec && (
          <p
            role="status"
            className={`rounded-md border p-3 text-sm ${
              rec.status === "raise" ? "border-primary bg-primary/5 text-fg" : "border-border bg-bg text-fg"
            }`}
          >
            {rec.message}
            {rec.status === "raise" && canWrite && " Eşiği Ayarlar'dan siz değiştirirsiniz; değişiklik denetim izine yazılır."}
          </p>
        )}
        <QualitySweep rows={m.sweep} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="trend-baslik" className="space-y-3 rounded-card border border-border bg-surface p-5">
          <h2 id="trend-baslik" className="text-sm font-semibold tracking-wide text-muted uppercase">
            Eğilim
          </h2>
          {q.history.length === 0 ? (
            <p className="text-sm text-muted">Henüz kayıtlı ölçüm yok. Haftalık ölçüm Pazartesi sabahı alınır.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-1 font-medium">Tarih</th>
                  <th className="py-1 text-right font-medium">Etiket</th>
                  <th className="py-1 text-right font-medium">Yanlış pozitif</th>
                  <th className="py-1 text-right font-medium">İnceleme</th>
                  <th className="py-1 text-right font-medium">Eşik</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-mono text-xs tabular-nums">
                {q.history.map((h) => (
                  <tr key={h.id}>
                    <td className="py-1.5 font-sans text-muted">
                      {new Date(h.created_at).toLocaleDateString("tr-TR")} · {REASON[h.reason] ?? h.reason}
                    </td>
                    <td className="py-1.5 text-right">{h.label_count}</td>
                    <td className="py-1.5 text-right">{pct(h.metrics.false_positive_rate)}</td>
                    <td className="py-1.5 text-right">{pct(h.metrics.review_rate)}</td>
                    <td className="py-1.5 text-right">{h.thresholds.auto_dismiss_below}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section aria-labelledby="haber-baslik" className="space-y-3 rounded-card border border-border bg-surface p-5">
          <h2 id="haber-baslik" className="text-sm font-semibold tracking-wide text-muted uppercase">
            Olumsuz haber (beta) isabeti
          </h2>
          <dl className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <dt className="text-xs text-muted">İncelenen</dt>
              <dd className="font-mono text-fg tabular-nums">
                {q.adverse_media.reviewed}/{q.adverse_media.candidates}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">İlgili payı</dt>
              <dd className="font-mono text-fg tabular-nums">{pct(q.adverse_media.precision)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Olumsuz terimli</dt>
              <dd className="font-mono text-fg tabular-nums">{pct(q.adverse_media.hint_precision)}</dd>
            </div>
          </dl>
          <p className="text-xs text-muted">
            Puana alınma ön koşulu: en az 100 incelenmiş haber ve %80 ilgili payı.{" "}
            {q.adverse_media.promotion_ready
              ? "Koşul sağlandı; karar sizin."
              : "Henüz sağlanmadı; haberler puana girmez."}
          </p>
        </section>
      </div>
    </div>
  );
}
