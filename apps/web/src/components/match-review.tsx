"use client";

// Eşleşme inceleme (HITL) — onayla / gerekçesiyle ele.
//
// Backend eleme kararında gerekçeyi ZORUNLU tutar (MASAK denetiminde "neden elendi"
// cevapsız kalamaz); arayüz aynı kuralı önden uygular ki kullanıcı 400 ile karşılaşmasın.

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { MatchCandidate } from "@/lib/screening";

export function MatchReview({
  screeningId,
  candidate,
}: {
  screeningId: string;
  candidate: MatchCandidate;
}) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "confirmed" | "dismissed") {
    if (decision === "dismissed" && !note.trim()) {
      setError("Eleme kararı için gerekçe zorunludur.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/screenings/${screeningId}/candidates/${candidate.id}/decision`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ decision, note: note.trim() || null }),
        },
      );
      if (!res.ok) {
        const payload = (await res.json().catch(() => null)) as {
          error?: { message?: string };
        } | null;
        setError(payload?.error?.message ?? "Karar kaydedilemedi.");
        return;
      }
      setNote("");
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-2 border-t border-border pt-3">
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Karar gerekçesi (eleme için zorunlu)"
        className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => decide("confirmed")}
          className="rounded-md border border-danger px-3 py-1.5 text-sm text-danger disabled:opacity-50"
        >
          Eşleşmeyi onayla
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => decide("dismissed")}
          className="rounded-md border border-border px-3 py-1.5 text-sm text-muted hover:text-fg disabled:opacity-50"
        >
          Gerekçesiyle ele
        </button>
      </div>
      {error !== null && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
