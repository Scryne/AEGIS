"use client";

// İzleme anahtarı (E2.4): açıkken varlık her gece yeni veri kümesiyle yeniden taranır ve
// önceki koşuya göre önemli bir fark "İzleme" sayfasında alarm olarak görünür.

import { useRouter } from "next/navigation";
import { useState } from "react";

export function MonitoringToggle({ entityId, monitored }: { entityId: string; monitored: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/entities/${entityId}/monitoring`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ monitored: !monitored }),
      });
      if (!res.ok) {
        setError("İzleme durumu değiştirilemedi.");
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
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-sm font-medium text-fg">Sürekli izleme</p>
        <p className="text-xs text-muted">
          {monitored
            ? "Her gece yeni liste verisiyle yeniden taranıyor; fark çıkarsa İzleme sayfasında alarm görünür."
            : "Kapalı. Açarsanız her gece yeniden taranır ve önceki sonuçla karşılaştırılır."}
        </p>
        {error && (
          <p role="alert" className="text-xs text-danger">
            {error}
          </p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={monitored}
        aria-label="Sürekli izleme"
        onClick={toggle}
        disabled={busy}
        className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors disabled:opacity-60 ${
          monitored ? "border-primary bg-primary" : "border-border bg-bg"
        }`}
      >
        <span
          aria-hidden="true"
          className={`absolute top-[2px] left-[2px] h-[18px] w-[18px] rounded-full border border-border bg-white shadow-sm transition-transform ${
            monitored ? "translate-x-[20px]" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}
