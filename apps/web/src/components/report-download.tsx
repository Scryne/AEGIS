"use client";

// Rapor indirme bağlantısı.
//
// Doğrudan <a href="/api/v1/reports/{id}/download"> OLMAZ: o uç dosyayı değil, kısa
// ömürlü **imzalı URL**'i JSON olarak döndürür (dosya API'den akıtılmaz). Bu bileşen
// önce bağlantıyı alır, sonra nesne deposuna yönlendirir.

import { useState } from "react";

export function ReportDownloadLink({ reportId }: { reportId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/reports/${reportId}/download`);
      const payload = (await res.json().catch(() => null)) as
        | { url?: string; error?: { message?: string } }
        | null;
      if (!res.ok || !payload?.url) {
        setError(payload?.error?.message ?? "İndirme bağlantısı alınamadı.");
        return;
      }
      window.open(payload.url, "_blank", "noopener,noreferrer");
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shrink-0 text-right">
      <button
        type="button"
        disabled={busy}
        onClick={download}
        className="text-xs text-fg underline disabled:opacity-50"
      >
        {busy ? "Hazırlanıyor…" : "İndir"}
      </button>
      {error !== null && (
        <p role="alert" className="text-[10px] text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
