// Risk özeti paneli — kural tabanlı, gerekçeleriyle (E1.5).
//
// Panel bir PUAN göstermez, kuralların ürettiği CÜMLELERİ gösterir: "neden bu seviye"
// sorusunun cevabı ekranda okunabilir olmalıdır (ADR-0008). Seviyeyi yükseltmeyen ama
// karar bekleyen bulgular "işlem bekliyor" olarak ayrı işaretlenir — yüksek skorlu bir
// eşleşme, insan onaylamadan dosyayı Yüksek yapmaz.

import type { RiskSummary } from "@/lib/reports";
import { RISK_CLASSES } from "@/lib/reports";

export function RiskSummaryPanel({ risk }: { risk: RiskSummary }) {
  return (
    <section className={`rounded-card border bg-surface p-5 ${RISK_CLASSES[risk.level]}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold tracking-wide uppercase">Risk değerlendirmesi</h2>
        <span className="text-lg font-semibold">{risk.level_label}</span>
      </div>
      <p className="mt-1 text-sm text-fg">{risk.rationale}</p>

      {!risk.complete && (
        <p className="mt-2 text-xs">
          Dosyada karar bekleyen bulgular var; değerlendirme tamamlanmamıştır.
        </p>
      )}

      {risk.findings.length > 0 ? (
        <ol className="mt-4 space-y-3">
          {risk.findings.map((finding) => (
            <li key={finding.code} className="border-t border-border pt-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-fg">{finding.title}</span>
                {finding.needs_action && (
                  <span className="rounded border border-warning px-1.5 py-0.5 text-[10px] text-warning uppercase">
                    işlem bekliyor
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-muted">{finding.rationale}</p>
              {finding.source_refs.length > 0 && (
                <p className="mt-1 text-[11px] text-muted">
                  Kaynak: {finding.source_refs.join(" · ")}
                </p>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 text-sm text-muted">Kuralların ürettiği bulgu yok.</p>
      )}

      <p className="mt-4 border-t border-border pt-3 text-[11px] text-muted">
        Bu özet bir karar desteği çıktısıdır; müşteri kabul, ret ya da şüpheli işlem
        bildirimi kararı yükümlü kuruma aittir.
      </p>
    </section>
  );
}
