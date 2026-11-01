"use client";

// Toplu tarama yükleme (E3.3): dosya → önizleme (önerilen sütun eşlemesi + ilk 20 satırın
// doğrulaması) → eşlemeyi düzelt → taslak olarak kaydet. Dosya önizlemede saklanmaz; kayıtta
// yalnız eşlenen alanlar tutulur. TCKN sütunu backend tarafından reddedilir.

import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { FIELD_LABELS } from "@/lib/batches";

interface Preview {
  headers: string[];
  suggested_mapping: Record<string, string | null>;
  mapping: Record<string, string>;
  national_id_columns: string[];
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  sample: {
    row_no: number;
    data: Record<string, string | null>;
    errors: string[];
    warnings: string[];
    duplicate_of: number | null;
  }[];
}

const FIELDS = ["name", "schema_type", "tax_number", "mersis_number", "country", "external_ref"];

async function errorText(res: Response, fallback: string): Promise<string> {
  const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
  return body?.error?.message ?? fallback;
}

export function BatchUpload() {
  const router = useRouter();
  const fileId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runPreview(f: File, map?: Record<string, string>) {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", f);
    if (map) form.append("mapping", JSON.stringify(map));
    try {
      const res = await fetch("/api/v1/batches/preview", { method: "POST", body: form });
      if (!res.ok) {
        setError(await errorText(res, "Dosya okunamadı."));
        setPreview(null);
        return;
      }
      const data = (await res.json()) as Preview;
      setPreview(data);
      setMapping(data.mapping);
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("mapping", JSON.stringify(mapping));
    try {
      const res = await fetch("/api/v1/batches", { method: "POST", body: form });
      if (!res.ok) {
        setError(await errorText(res, "Toplu iş kaydedilemedi."));
        return;
      }
      const body = (await res.json()) as { id: string };
      router.push(`/batches/${body.id}`);
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  function changeMapping(field: string, header: string) {
    const next = { ...mapping };
    if (header) next[field] = header;
    else delete next[field];
    setMapping(next);
    if (file) void runPreview(file, next);
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <label htmlFor={fileId} className="block text-sm font-medium text-fg">
          CSV dosyası
        </label>
        <input
          id={fileId}
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setFile(f);
            setPreview(null);
            if (f) void runPreview(f);
          }}
          className="block w-full text-sm text-fg file:mr-3 file:rounded-md file:border file:border-border file:bg-surface file:px-3 file:py-1.5 file:text-sm"
        />
        <p className="text-xs text-muted">
          Excel&apos;den &quot;CSV (noktalı virgülle ayrılmış)&quot; olarak kaydedin. En çok 1.000 satır. TCKN
          sütunu alınmaz; kişileri kimlik numarasıyla varlık formundan ekleyin.
        </p>
      </div>

      {error && (
        <p role="alert" className="rounded-md border border-danger bg-surface p-3 text-sm text-danger">
          {error}
        </p>
      )}

      {preview && (
        <div className="space-y-4">
          {preview.national_id_columns.length > 0 && (
            <p className="rounded-md border border-warning bg-warning/10 p-3 text-sm text-fg">
              Dosyada TCKN sütunu var ({preview.national_id_columns.join(", ")}). Bu sütun eşlenmez ve
              saklanmaz.
            </p>
          )}
          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="mb-2 text-sm font-semibold text-fg">Sütun eşlemesi</legend>
            {FIELDS.map((f) => (
              <label key={f} className="space-y-1 text-sm">
                <span className="block text-xs text-muted">
                  {FIELD_LABELS[f]}
                  {f === "name" && " (zorunlu)"}
                </span>
                <select
                  value={mapping[f] ?? ""}
                  onChange={(e) => changeMapping(f, e.target.value)}
                  className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-fg"
                >
                  <option value="">— eşleme yok —</option>
                  {preview.headers
                    .filter((h) => !preview.national_id_columns.includes(h))
                    .map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                </select>
              </label>
            ))}
          </fieldset>

          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Satır", preview.total_rows, "text-fg"],
              ["Taranacak", preview.valid_rows, "text-fg"],
              ["Geçersiz", preview.invalid_rows, preview.invalid_rows ? "text-danger" : "text-fg"],
              ["Dosyada tekrar", preview.duplicate_rows, "text-fg"],
            ].map(([label, value, tone]) => (
              <div key={String(label)} className="rounded-card border border-border bg-surface px-4 py-3">
                <dt className="text-xs text-muted">{label}</dt>
                <dd className={`mt-1 font-mono text-xl tabular-nums ${tone}`}>{value}</dd>
              </div>
            ))}
          </dl>

          <div className="overflow-x-auto rounded-card border border-border">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <caption className="sr-only">İlk 20 satırın önizlemesi</caption>
              <thead className="bg-bg text-xs text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Satır</th>
                  <th className="px-3 py-2 font-medium">Ad / unvan</th>
                  <th className="px-3 py-2 font-medium">Tür</th>
                  <th className="px-3 py-2 font-medium">Vergi no</th>
                  <th className="px-3 py-2 font-medium">Durum</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {preview.sample.map((r) => (
                  <tr key={r.row_no}>
                    <td className="px-3 py-2 font-mono text-xs text-muted tabular-nums">{r.row_no}</td>
                    <td className="px-3 py-2 text-fg">{r.data.name || "—"}</td>
                    <td className="px-3 py-2 text-muted">{r.data.schema_type === "Person" ? "Kişi" : "Şirket"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{r.data.tax_number ?? "—"}</td>
                    <td className="px-3 py-2 text-xs">
                      {r.errors.length > 0 ? (
                        <span className="text-danger">{r.errors.join(" ")}</span>
                      ) : r.duplicate_of ? (
                        <span className="text-muted">{r.duplicate_of}. satırın tekrarı</span>
                      ) : r.warnings.length > 0 ? (
                        <span className="text-fg">{r.warnings.join(" ")}</span>
                      ) : (
                        <span className="text-muted">Hazır</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button
            type="button"
            onClick={create}
            disabled={busy || !mapping.name || preview.valid_rows === 0}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-fg disabled:opacity-50"
          >
            {busy ? "Kaydediliyor…" : `Taslak olarak kaydet (${preview.valid_rows} satır)`}
          </button>
        </div>
      )}
    </div>
  );
}
