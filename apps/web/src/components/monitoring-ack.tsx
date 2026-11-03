"use client";

// Alarm onayı: gerekçe zorunlu (MASAK denetiminde "bu farkı gördünüz mü, ne yaptınız"
// sorusunun cevabı). Alarm silinmez; durumu "görüldü" olur.

import { useRouter } from "next/navigation";
import { useState } from "react";

export function MonitoringAck({ alertId }: { alertId: string }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (note.trim().length < 3) {
      setError("Ne yaptığınızı kısaca yazın (en az 3 karakter).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/monitoring/alerts/${alertId}/acknowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: note.trim() }),
      });
      if (!res.ok) {
        setError("Alarm kaydedilemedi.");
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
    <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-start">
      <label htmlFor={`not-${alertId}`} className="sr-only">
        Alarm notu
      </label>
      <input
        id={`not-${alertId}`}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Ne yapıldı? (ör. eşleşme incelemeye alındı)"
        className="field min-w-0 flex-1"
      />
      <button
        type="submit"
        disabled={busy}
        className="btn-primary"
      >
        {busy ? "Kaydediliyor…" : "Görüldü olarak işaretle"}
      </button>
      {error && (
        <p role="alert" className="text-xs text-danger sm:basis-full">
          {error}
        </p>
      )}
    </form>
  );
}
