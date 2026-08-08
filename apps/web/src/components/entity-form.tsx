"use client";

// Yeni varlık formu — yazarken **mükerrer kayıt kontrolü** yapar.
//
// Kullanıcı unvanı/vergi numarasını girerken /entities/resolve sorulur; aynı şirket
// kütükte varsa kayıt açılmadan önce gösterilir. Mükerrer müşteri kaydı, dosyaların
// ikiye bölünmesine ve tarama geçmişinin kopmasına yol açar — en ucuz önlem, kaydı
// açmadan önce sormaktır.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { IdentifierWarning, ResolutionResult } from "@/lib/entities";

export function EntityForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [schemaType, setSchemaType] = useState<"Company" | "Person">("Company");
  const [taxNumber, setTaxNumber] = useState("");
  const [nationalId, setNationalId] = useState("");
  const [address, setAddress] = useState("");
  const [duplicate, setDuplicate] = useState<ResolutionResult | null>(null);
  const [warnings, setWarnings] = useState<IdentifierWarning[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function checkDuplicate() {
    if (name.trim().length < 3) return;
    try {
      const res = await fetch("/api/v1/entities/resolve", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          schema_type: schemaType,
          tax_number: taxNumber.trim() || null,
          national_id: nationalId.trim() || null,
        }),
      });
      if (!res.ok) return;
      const result = (await res.json()) as ResolutionResult;
      setDuplicate(result.candidates.length > 0 ? result : null);
    } catch {
      // Sessiz: mükerrer kontrolü yardımcı bir özelliktir, kayıt açmayı engellemez.
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setWarnings([]);
    try {
      const res = await fetch("/api/v1/entities", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          schema_type: schemaType,
          tax_number: taxNumber.trim() || null,
          national_id: nationalId.trim() || null,
          address: address.trim() || null,
          country: "tr",
        }),
      });
      const payload = (await res.json().catch(() => null)) as
        | {
            entity?: { id: string };
            identifier_warnings?: IdentifierWarning[];
            error?: { message?: string };
          }
        | null;
      if (!res.ok) {
        setError(payload?.error?.message ?? "Kayıt oluşturulamadı.");
        return;
      }
      // Uyarı varsa kayıt YAPILDI ama kullanıcı görsün diye önce gösterilir.
      if (payload?.identifier_warnings?.length) {
        setWarnings(payload.identifier_warnings);
      }
      router.push(`/entities/${payload?.entity?.id}`);
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">
            {schemaType === "Company" ? "Ticaret unvanı" : "Ad soyad"}
          </span>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={checkDuplicate}
            placeholder="Örn. Yıldız İnşaat San. ve Tic. Ltd. Şti."
            className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Tür</span>
          <select
            value={schemaType}
            onChange={(e) => setSchemaType(e.target.value as "Company" | "Person")}
            className="rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
          >
            <option value="Company">Tüzel kişi</option>
            <option value="Person">Gerçek kişi</option>
          </select>
        </label>
      </div>

      {schemaType === "Company" ? (
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Vergi numarası</span>
          <input
            value={taxNumber}
            onChange={(e) => setTaxNumber(e.target.value)}
            onBlur={checkDuplicate}
            inputMode="numeric"
            className="w-full rounded-md border border-border bg-bg px-3 py-2 font-mono text-sm text-fg"
          />
        </label>
      ) : (
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">T.C. kimlik numarası</span>
          <input
            value={nationalId}
            onChange={(e) => setNationalId(e.target.value)}
            onBlur={checkDuplicate}
            inputMode="numeric"
            className="w-full rounded-md border border-border bg-bg px-3 py-2 font-mono text-sm text-fg"
          />
          <span className="mt-1 block text-xs text-muted">
            Şifreli saklanır; ekranlarda yalnız son 4 hanesi görünür.
          </span>
        </label>
      )}

      <label className="block">
        <span className="mb-1 block text-xs font-medium text-muted">Adres</span>
        <input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
        />
      </label>

      {duplicate !== null && (
        <div className="rounded-card border border-warning bg-surface p-3 text-sm text-warning">
          <strong className="font-semibold">Benzer kayıt(lar) bulundu.</strong>
          <ul className="mt-2 space-y-1">
            {duplicate.candidates.map((candidate) => (
              <li key={candidate.entity_id} className="flex justify-between gap-3">
                <Link href={`/entities/${candidate.entity_id}`} className="underline">
                  {candidate.name}
                </Link>
                <span className="text-xs">{candidate.reason}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs">
            Aynı şirketse mevcut kaydı açın; farklıysa kayda devam edebilirsiniz.
          </p>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="rounded-card border border-warning bg-surface p-3 text-sm text-warning">
          {warnings.map((warning) => (
            <p key={warning.field}>{warning.message}</p>
          ))}
        </div>
      )}

      {error !== null && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={busy || !name.trim()}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-fg disabled:opacity-50"
      >
        {busy ? "Kaydediliyor…" : "Kaydı oluştur"}
      </button>
    </form>
  );
}
