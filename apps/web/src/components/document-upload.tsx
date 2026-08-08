"use client";

// Belge yükleme — imza sirküleri / faaliyet belgesi / Ticaret Sicil Gazetesi.
//
// Gazete seçildiğinde sayı/tarih/bağlantı alanları açılır: Revizyon R1 gereği otomatik
// gazete sorgusu YOKTUR, kullanıcı kaynağı elle bildirir ve bu bilgi raporda kanıt
// referansı olarak görünür.

import { useRouter } from "next/navigation";
import { useState } from "react";

const DOC_TYPES = [
  { value: "imza_sirkuleri", label: "İmza sirküleri" },
  { value: "faaliyet_belgesi", label: "Faaliyet belgesi" },
  { value: "ticaret_sicil_gazetesi", label: "Ticaret Sicil Gazetesi" },
  { value: "other", label: "Diğer (çıkarım yapılmaz)" },
] as const;

export function DocumentUpload({ entityId }: { entityId: string }) {
  const router = useRouter();
  const [docType, setDocType] = useState<string>("faaliyet_belgesi");
  const [file, setFile] = useState<File | null>(null);
  const [issueNumber, setIssueNumber] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [gazetteUrl, setGazetteUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isGazette = docType === "ticaret_sicil_gazetesi";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (file === null) return;
    setBusy(true);
    setError(null);

    const form = new FormData();
    form.append("file", file);
    form.append("entity_id", entityId);
    form.append("doc_type", docType);
    if (isGazette) {
      if (issueNumber.trim()) form.append("gazette_issue_number", issueNumber.trim());
      if (issueDate) form.append("gazette_issue_date", issueDate);
      if (gazetteUrl.trim()) form.append("gazette_url", gazetteUrl.trim());
    }

    try {
      const res = await fetch("/api/v1/documents", { method: "POST", body: form });
      if (!res.ok) {
        const payload = (await res.json().catch(() => null)) as {
          error?: { message?: string };
        } | null;
        setError(payload?.error?.message ?? "Belge yüklenemedi.");
        return;
      }
      setFile(null);
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Belge türü</span>
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
          >
            {DOC_TYPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Dosya</span>
          <input
            required
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="w-full text-sm text-fg"
          />
        </label>
      </div>

      {isGazette && (
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Gazete sayısı</span>
            <input
              value={issueNumber}
              onChange={(e) => setIssueNumber(e.target.value)}
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Yayım tarihi</span>
            <input
              type="date"
              value={issueDate}
              onChange={(e) => setIssueDate(e.target.value)}
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">Bağlantı</span>
            <input
              value={gazetteUrl}
              onChange={(e) => setGazetteUrl(e.target.value)}
              placeholder="https://www.ticaretsicil.gov.tr/..."
              className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
            />
          </label>
        </div>
      )}

      {error !== null && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={busy || file === null}
        className="rounded-md border border-border px-3 py-1.5 text-sm text-fg disabled:opacity-50"
      >
        {busy ? "Yükleniyor…" : "Belgeyi yükle"}
      </button>
    </form>
  );
}
