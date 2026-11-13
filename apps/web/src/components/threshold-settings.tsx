"use client";

// Tarama eşik bandı: skor 0–1 ekseninde dört bölge. Değişiklik gerekçesiz kaydedilmez; gerekçe
// denetim olayına yazılır (MASAK incelemesinde "eşik neden değişti" sorusunun cevabı). Sunucu
// bandı yeniden doğrular; buradaki denetim yalnız erken uyarıdır.

import { useRouter } from "next/navigation";
import { useId, useState } from "react";

export interface Thresholds {
  candidate_cutoff: number;
  auto_dismiss_below: number;
  auto_flag_at: number;
}

const FIELDS: { key: keyof Thresholds; label: string; hint: string }[] = [
  {
    key: "candidate_cutoff",
    label: "Aday alt sınırı",
    hint: "Bu skorun altındaki adaylar motordan hiç dönmez.",
  },
  {
    key: "auto_dismiss_below",
    label: "Otomatik eleme sınırı",
    hint: "Bu skorun altındaki adaylar gerekçesiyle kendiliğinden elenir.",
  },
  {
    key: "auto_flag_at",
    label: "İşaretleme sınırı",
    hint: "Bu skor ve üstü acil inceleme olarak işaretlenir.",
  },
];

function bandError(t: Thresholds): string | null {
  for (const field of FIELDS) {
    const v = t[field.key];
    if (!Number.isFinite(v) || v < 0 || v > 1) return `${field.label} 0 ile 1 arasında olmalı.`;
  }
  if (t.candidate_cutoff > t.auto_dismiss_below)
    return "Aday alt sınırı, otomatik eleme sınırından büyük olamaz; aksi hâlde elenenlerin bir kısmı hiç görünmez.";
  if (t.auto_dismiss_below > t.auto_flag_at) return "Otomatik eleme sınırı, işaretleme sınırından büyük olamaz.";
  return null;
}

const fmt = (v: number) => (Number.isFinite(v) ? v.toFixed(2) : "—");

/** Skor ekseni: dört bölge, her biri metinle de adlandırılır (renk tek başına anlam taşımaz). */
export function ThresholdBand({ t }: { t: Thresholds }) {
  const c = Math.min(Math.max(t.candidate_cutoff, 0), 1);
  const d = Math.min(Math.max(t.auto_dismiss_below, c), 1);
  const f = Math.min(Math.max(t.auto_flag_at, d), 1);
  const zones = [
    { label: "Gösterilmez", range: `0,00 – ${fmt(c)}`, width: c, cls: "bg-subtle" },
    { label: "Kendiliğinden elenir", range: `${fmt(c)} – ${fmt(d)}`, width: d - c, cls: "bg-border-strong" },
    { label: "İnsan incelemesi", range: `${fmt(d)} – ${fmt(f)}`, width: f - d, cls: "bg-warning" },
    { label: "Acil inceleme", range: `${fmt(f)} – 1,00`, width: 1 - f, cls: "bg-danger" },
  ];
  return (
    <figure className="space-y-3">
      <div className="flex h-3 overflow-hidden rounded-full border border-border" aria-hidden="true">
        {zones.map((z) => (
          <div key={z.label} className={z.cls} style={{ width: `${z.width * 100}%` }} />
        ))}
      </div>
      <figcaption>
        <ul className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
          {zones.map((z) => (
            <li key={z.label} className="flex items-start gap-2">
              <span className={`mt-0.5 size-2.5 shrink-0 rounded-sm border border-border ${z.cls}`} aria-hidden="true" />
              <span>
                <span className="block text-fg">{z.label}</span>
                <span className="font-mono text-muted tabular-nums">{z.range.replaceAll(".", ",")}</span>
              </span>
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}

export function ThresholdSettings({ initial, canEdit }: { initial: Thresholds; canEdit: boolean }) {
  const router = useRouter();
  const noteId = useId();
  const [values, setValues] = useState<Record<keyof Thresholds, string>>({
    candidate_cutoff: String(initial.candidate_cutoff),
    auto_dismiss_below: String(initial.auto_dismiss_below),
    auto_flag_at: String(initial.auto_flag_at),
  });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  const parsed: Thresholds = {
    candidate_cutoff: Number(values.candidate_cutoff.replace(",", ".")),
    auto_dismiss_below: Number(values.auto_dismiss_below.replace(",", ".")),
    auto_flag_at: Number(values.auto_flag_at.replace(",", ".")),
  };
  const invalid = bandError(parsed);
  const changed = FIELDS.some((f) => parsed[f.key] !== initial[f.key]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (invalid) {
      setMessage({ tone: "error", text: invalid });
      return;
    }
    if (note.trim().length < 10) {
      setMessage({ tone: "error", text: "Değişikliğin gerekçesini en az 10 karakterle yazın; denetim izine girer." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/v1/settings/screening.thresholds", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: parsed, note: note.trim() }),
      });
      if (!res.ok) {
        const payload = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
        setMessage({
          tone: "error",
          text: payload?.error?.message ?? "Eşik kaydedilemedi. Yetkinizi denetleyip yeniden deneyin.",
        });
        return;
      }
      setNote("");
      setMessage({ tone: "ok", text: "Eşik bandı kaydedildi; sonraki taramalar bu bantla çalışır ve değişiklik denetim izine yazıldı." });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-5" noValidate>
      <ThresholdBand t={invalid ? initial : parsed} />

      <fieldset disabled={!canEdit || busy} className="space-y-4">
        <legend className="sr-only">Eşik değerleri</legend>
        <div className="grid gap-4 sm:grid-cols-3">
          {FIELDS.map((field) => (
            <label key={field.key} className="block space-y-1.5">
              <span className="block text-sm font-medium text-fg">{field.label}</span>
              <input
                type="number"
                inputMode="decimal"
                min={0}
                max={1}
                step={0.01}
                value={values[field.key]}
                onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                aria-invalid={Boolean(invalid)}
                className="field font-mono tabular-nums"
              />
              <span className="block text-xs text-muted">{field.hint}</span>
            </label>
          ))}
        </div>

        {canEdit && (
          <>
            <label htmlFor={noteId} className="block space-y-1.5">
              <span className="block text-sm font-medium text-fg">Gerekçe</span>
              <textarea
                id={noteId}
                rows={2}
                maxLength={1000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Ör. Kalite ölçümü 0,70'te onaylı eşleşme kaybı olmadığını gösterdi (42 karar)."
                className="field resize-y"
              />
              <span className="block text-xs text-muted">Denetim izine değişiklikle birlikte yazılır.</span>
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <button type="submit" disabled={busy || !changed} className="btn-primary">
                {busy ? "Kaydediliyor…" : "Eşik bandını kaydet"}
              </button>
              {!changed && <span className="text-xs text-muted">Kaydetmek için bir değeri değiştirin.</span>}
            </div>
          </>
        )}
      </fieldset>

      {invalid && !message && (
        <p role="alert" className="text-sm text-danger">
          {invalid}
        </p>
      )}
      {message && (
        <p
          role={message.tone === "error" ? "alert" : "status"}
          className={`text-sm ${message.tone === "error" ? "text-danger" : "text-success"}`}
        >
          {message.text}
        </p>
      )}
    </form>
  );
}
