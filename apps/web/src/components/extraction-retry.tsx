"use client";

// Çıkarımı yeniden dene — başarısız ya da atlanmış (motor kurulu değilken yüklenmiş)
// belgeyi yeniden kuyruğa alır. Görev idempotent olduğu için bu yol olmadan belge bir
// daha işlenemezdi. Öneriler yine insan onayı bekler (Revizyon R2).

import { useRouter } from "next/navigation";
import { useState } from "react";

export function ExtractionRetry({ documentId }: { documentId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function retry() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/documents/${documentId}/extract`, { method: "POST" });
      if (!res.ok) {
        const payload = (await res.json().catch(() => null)) as {
          error?: { message?: string };
        } | null;
        setError(payload?.error?.message ?? "Çıkarım yeniden başlatılamadı. Tekrar deneyin.");
        return;
      }
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={retry}
        disabled={busy}
        className="rounded border border-border px-2 py-0.5 text-xs text-fg hover:bg-bg disabled:opacity-50"
      >
        {busy ? "Kuyruğa alınıyor…" : "Çıkarımı yeniden dene"}
      </button>
      {error !== null && (
        <p role="alert" className="mt-1 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
