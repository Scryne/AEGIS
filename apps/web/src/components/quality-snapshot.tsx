"use client";

// Ölçümü kayda geçir (E3.6): eşik değişikliğinden önce ve sonra alınan kayıtlar eğilimi gösterir.

import { useRouter } from "next/navigation";
import { useState } from "react";

export function QualitySnapshotButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="space-y-1 text-right">
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const res = await fetch("/api/v1/quality/matching/snapshot", { method: "POST" });
            if (!res.ok) setError("Ölçüm kaydedilemedi.");
            else router.refresh();
          } catch {
            setError("Sunucuya ulaşılamadı.");
          } finally {
            setBusy(false);
          }
        }}
        className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium text-fg disabled:opacity-50"
      >
        {busy ? "Kaydediliyor…" : "Ölçümü kayda geçir"}
      </button>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
