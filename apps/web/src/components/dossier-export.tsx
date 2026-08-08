"use client";

// Dosya dışa aktarma — PDF / Word.
//
// Dışa aktarma bir OKUMA değildir: kütüğe rapor satırı yazar ve denetim izine
// `report.export` olayı düşer. Bu yüzden salt-okunur denetçiye (auditor) hiç
// gösterilmez; sayfa ayrıca backend'de de kapılıdır (RBAC).
//
// İndirme, imzalı kısa ömürlü URL üzerinden yapılır; dosya API'den akıtılmaz.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ReportDownloadLink } from "@/components/report-download";
import type { Report } from "@/lib/reports";

export function DossierExport({ entityId }: { entityId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState<Report | null>(null);

  async function exportDossier(reportFormat: "pdf" | "docx") {
    setBusy(reportFormat);
    setError(null);
    setReady(null);
    try {
      const res = await fetch("/api/v1/reports/dossier", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ entity_id: entityId, report_format: reportFormat }),
      });
      const payload = (await res.json().catch(() => null)) as
        | (Report & { error?: { message?: string } })
        | null;
      if (!res.ok || payload === null) {
        setError(payload?.error?.message ?? "Rapor üretilemedi.");
        return;
      }
      setReady(payload);
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => exportDossier("pdf")}
          className="rounded-md border border-border px-3 py-1.5 text-sm text-fg disabled:opacity-50"
        >
          {busy === "pdf" ? "Üretiliyor…" : "Dosyayı PDF olarak dışa aktar"}
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => exportDossier("docx")}
          className="rounded-md border border-border px-3 py-1.5 text-sm text-fg disabled:opacity-50"
        >
          {busy === "docx" ? "Üretiliyor…" : "Word olarak dışa aktar"}
        </button>
      </div>
      {ready !== null && (
        <div className="flex items-center gap-3">
          <p className="text-sm text-success">Rapor üretildi ve saklandı.</p>
          <ReportDownloadLink reportId={ready.id} />
        </div>
      )}
      {error !== null && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
