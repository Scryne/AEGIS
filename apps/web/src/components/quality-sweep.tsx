// Eşik taraması (E3.6): her aday otomatik eleme eşiğinde "kaç inceleme azalırdı" (çubuk) ve
// "kaç onaylı eşleşme kaybolurdu" (kırmızı işaret + sayı). Tek eksen, aynı birim (karar sayısı).
// Kimlik renkle değil metinle de verilir (lejant + tablo görünümü); fareyle üzerine gelince
// SVG <title> değeri söyler.

interface SweepRow {
  threshold: number;
  saved_reviews: number;
  lost_confirmed: number;
  current: boolean;
}

export function QualitySweep({ rows }: { rows: SweepRow[] }) {
  const w = 640;
  const h = 180;
  const pad = { l: 32, r: 8, t: 12, b: 28 };
  const max = Math.max(1, ...rows.map((r) => Math.max(r.saved_reviews, r.lost_confirmed)));
  const step = (w - pad.l - pad.r) / rows.length;
  const y = (v: number) => pad.t + (h - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, Math.round(max / 2), max];

  return (
    <figure className="space-y-2">
      <div className="flex flex-wrap gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block size-2.5 rounded-sm bg-primary" /> Azalacak inceleme
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block size-2.5 rounded-full bg-danger" /> Kaybolacak onaylı eşleşme
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-3 w-0.5 bg-fg" /> Mevcut eşik
        </span>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="Otomatik eleme eşiğine göre azalacak inceleme ve kaybolacak onaylı eşleşme sayısı"
        className="h-auto w-full"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} className="stroke-border" strokeWidth={1} />
            <text x={pad.l - 6} y={y(t) + 3} textAnchor="end" className="fill-muted text-[10px]">
              {t}
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const x = pad.l + i * step;
          const bw = Math.max(2, step - 4);
          const top = y(r.saved_reviews);
          return (
            <g key={r.threshold}>
              <title>
                {`Eşik ${r.threshold.toFixed(3)}: ${r.saved_reviews} inceleme azalır, ${r.lost_confirmed} onaylı eşleşme kaybolur`}
              </title>
              <rect x={x} y={pad.t} width={step} height={h - pad.t - pad.b} fill="transparent" />
              {r.saved_reviews > 0 && (
                <rect
                  x={x + 2}
                  y={top}
                  width={bw}
                  height={h - pad.b - top}
                  rx={2}
                  className="fill-primary"
                  opacity={r.lost_confirmed > 0 ? 0.35 : 1}
                />
              )}
              {r.lost_confirmed > 0 && (
                <circle
                  cx={x + step / 2}
                  cy={y(r.lost_confirmed)}
                  r={4}
                  className="fill-danger stroke-surface"
                  strokeWidth={2}
                />
              )}
              {r.current && (
                <line x1={x + step / 2} x2={x + step / 2} y1={pad.t} y2={h - pad.b} className="stroke-fg" strokeWidth={2} />
              )}
              {i % 4 === 0 && (
                <text x={x + step / 2} y={h - 10} textAnchor="middle" className="fill-muted text-[10px]">
                  {r.threshold.toFixed(2)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <details className="text-xs">
        <summary className="cursor-pointer text-muted">Tablo olarak göster</summary>
        <table className="mt-2 w-full max-w-md text-left">
          <thead className="text-muted">
            <tr>
              <th className="py-1 font-medium">Eşik</th>
              <th className="py-1 text-right font-medium">Azalacak inceleme</th>
              <th className="py-1 text-right font-medium">Kaybolacak onaylı</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {rows.map((r) => (
              <tr key={r.threshold} className={r.current ? "font-semibold text-fg" : "text-fg"}>
                <td className="py-0.5">
                  {r.threshold.toFixed(3)}
                  {r.current && " (mevcut)"}
                </td>
                <td className="py-0.5 text-right">{r.saved_reviews}</td>
                <td className={`py-0.5 text-right ${r.lost_confirmed > 0 ? "text-danger" : ""}`}>{r.lost_confirmed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
