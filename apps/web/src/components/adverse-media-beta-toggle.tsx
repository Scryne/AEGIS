"use client";

// Olumsuz haber betası anahtarı (E2.5): yalnız hesap sahibi açar; kapatmak adayları silmez.

import { useRouter } from "next/navigation";
import { useState } from "react";

export function AdverseMediaBetaToggle({ enabled }: { enabled: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/adverse-media/beta", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !enabled }),
      });
      if (!res.ok) {
        setError("Beta durumu değiştirilemedi.");
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
        <p className="text-sm font-medium text-fg">Olumsuz haber taraması (beta)</p>
        <p className="max-w-prose text-xs text-muted">
          Varlık sayfasında Türkçe haber başlıklarını adla arar. Sonuçlar risk puanına girmez; her
          aday için ilgili/ilgisiz kararını ekibiniz verir.
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
        aria-checked={enabled}
        aria-label="Olumsuz haber betası"
        onClick={toggle}
        disabled={busy}
        className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors disabled:opacity-60 ${
          enabled ? "border-primary bg-primary" : "border-border bg-bg"
        }`}
      >
        <span
          aria-hidden="true"
          className={`absolute top-[2px] left-[2px] h-[18px] w-[18px] rounded-full border border-border bg-white shadow-sm transition-transform ${
            enabled ? "translate-x-[20px]" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}
