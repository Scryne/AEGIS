"use client";

// Tutarsızlık kararı — beyan ile belge/kütük verisi çeliştiğinde.
//
// Gerekçe ZORUNLUDUR: MASAK denetiminde "bu fark neden kabul edildi" sorusu cevapsız
// kalamaz. Kayıt kapatılmaz, karara bağlanır ve dosya raporunda görünmeye devam eder.

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Discrepancy } from "@/lib/entities";
import { SEVERITY_CLASSES, SEVERITY_LABELS, SOURCE_LABELS, attributeLabel } from "@/lib/entities";

export function DiscrepancyReview({
  discrepancy,
  canDecide,
}: {
  discrepancy: Discrepancy;
  canDecide: boolean;
}) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(status: "accepted" | "resolved") {
    if (!note.trim()) {
      setError("Gerekçe zorunludur.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/entities/${discrepancy.entity_id}/discrepancies/${discrepancy.id}/decision`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ status, note: note.trim() }),
        },
      );
      if (!res.ok) {
        const payload = (await res.json().catch(() => null)) as {
          error?: { message?: string };
        } | null;
        setError(payload?.error?.message ?? "Karar kaydedilemedi.");
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
    <li className={`rounded-card border bg-bg p-3 ${SEVERITY_CLASSES[discrepancy.severity]}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-medium">{attributeLabel(discrepancy.attribute_name)}</div>
        <span className="shrink-0 rounded border px-2 py-0.5 text-xs">
          {SEVERITY_LABELS[discrepancy.severity] ?? discrepancy.severity}
        </span>
      </div>

      <dl className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-muted">Beyan</dt>
          <dd className="text-fg">{discrepancy.declared_value}</dd>
        </div>
        <div>
          <dt className="text-muted">
            {SOURCE_LABELS[discrepancy.observed_source_type] ?? discrepancy.observed_source_type}
          </dt>
          <dd className="text-fg">{discrepancy.observed_value}</dd>
        </div>
      </dl>

      {discrepancy.observed_source_ref !== null && (
        <p className="mt-1 text-[11px] text-muted">Kaynak: {discrepancy.observed_source_ref}</p>
      )}

      {discrepancy.status !== "open" ? (
        <p className="mt-2 text-xs text-muted">
          <span className="font-medium">
            {discrepancy.status === "accepted" ? "Kabul edildi" : "Düzeltildi"}:
          </span>{" "}
          {discrepancy.resolution_note}
        </p>
      ) : (
        canDecide && (
          <div className="mt-3 space-y-2 border-t border-border pt-3">
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Gerekçe (zorunlu)"
              className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-fg"
            />
            <div className="flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => decide("accepted")}
                className="rounded-md border border-border px-3 py-1.5 text-sm text-fg disabled:opacity-50"
              >
                Açıklandı, kabul et
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => decide("resolved")}
                className="rounded-md border border-border px-3 py-1.5 text-sm text-muted disabled:opacity-50"
              >
                Düzeltildi
              </button>
            </div>
          </div>
        )
      )}

      {error !== null && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
    </li>
  );
}
