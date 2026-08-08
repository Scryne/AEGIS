"use client";

// Tarama başlatma formu — şirket + (isteğe bağlı) yönetici/gerçek faydalanıcı.
//
// İstek aynı-origin proxy'ye gider (/api/v1/screenings); token tarayıcıya açılmaz.
// 502 yanıtı da bir SONUÇTUR: kayıt oluşmuştur ve kullanıcı "tarama yapılamadı"
// uyarısını görmek üzere detay sayfasına yönlendirilir.

import { useRouter } from "next/navigation";
import { useState } from "react";

interface RelatedSubject {
  name: string;
  role: "officer" | "ubo" | "shareholder";
}

const ROLE_OPTIONS: { value: RelatedSubject["role"]; label: string }[] = [
  { value: "officer", label: "Yönetici" },
  { value: "ubo", label: "Gerçek faydalanıcı" },
  { value: "shareholder", label: "Ortak" },
];

export function ScreeningForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [subjectType, setSubjectType] = useState<"company" | "person">("company");
  const [taxNumber, setTaxNumber] = useState("");
  const [related, setRelated] = useState<RelatedSubject[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addRelated() {
    setRelated([...related, { name: "", role: "officer" }]);
  }

  function updateRelated(index: number, patch: Partial<RelatedSubject>) {
    setRelated(related.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }

  function removeRelated(index: number) {
    setRelated(related.filter((_, i) => i !== index));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    const identifiers: Record<string, string> = {};
    if (taxNumber.trim()) identifiers.taxNumber = taxNumber.trim();

    const body = {
      subject: {
        name: name.trim(),
        subject_type: subjectType,
        role: "self",
        country: "tr",
        identifiers,
      },
      related_subjects: related
        .filter((item) => item.name.trim())
        .map((item) => ({
          name: item.name.trim(),
          subject_type: "person" as const,
          role: item.role,
          country: "tr",
          identifiers: {},
        })),
    };

    try {
      const res = await fetch("/api/v1/screenings", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = (await res.json().catch(() => null)) as
        | { id?: string; error?: { message?: string } }
        | null;

      // 502 = motor erişilemedi. Kayıt yine de oluştu; kullanıcıyı oraya götürüp
      // "tarama YAPILAMADI" uyarısını gösteriyoruz — sessizce "temiz" demiyoruz.
      if (res.ok || (res.status === 502 && payload?.id)) {
        router.push(`/screenings/${payload?.id}`);
        router.refresh();
        return;
      }
      setError(payload?.error?.message ?? "Tarama başlatılamadı.");
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
            {subjectType === "company" ? "Şirket unvanı" : "Ad soyad"}
          </span>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Örn. Yıldız İnşaat San. ve Tic. Ltd. Şti."
            className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted">Tür</span>
          <select
            value={subjectType}
            onChange={(e) => setSubjectType(e.target.value as "company" | "person")}
            className="rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
          >
            <option value="company">Tüzel kişi</option>
            <option value="person">Gerçek kişi</option>
          </select>
        </label>
      </div>

      <label className="block">
        <span className="mb-1 block text-xs font-medium text-muted">
          Vergi numarası (isteğe bağlı)
        </span>
        <input
          value={taxNumber}
          onChange={(e) => setTaxNumber(e.target.value)}
          inputMode="numeric"
          className="w-full rounded-md border border-border bg-bg px-3 py-2 font-mono text-sm text-fg"
        />
        <span className="mt-1 block text-xs text-muted">
          Numara yalnız sorguda kullanılır; kayıtta maskeli saklanır.
        </span>
      </label>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted">
            Birlikte taranacak kişiler (yönetici / gerçek faydalanıcı)
          </span>
          <button
            type="button"
            onClick={addRelated}
            className="rounded-md border border-border px-2 py-1 text-xs text-muted hover:text-fg"
          >
            + Kişi ekle
          </button>
        </div>
        {related.map((item, index) => (
          <div key={index} className="flex gap-2">
            <input
              value={item.name}
              onChange={(e) => updateRelated(index, { name: e.target.value })}
              placeholder="Ad soyad"
              className="flex-1 rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
            />
            <select
              value={item.role}
              onChange={(e) =>
                updateRelated(index, { role: e.target.value as RelatedSubject["role"] })
              }
              className="rounded-md border border-border bg-bg px-2 py-2 text-sm text-fg"
            >
              {ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => removeRelated(index)}
              className="rounded-md border border-border px-2 text-sm text-muted hover:text-danger"
              aria-label="Kişiyi kaldır"
            >
              ×
            </button>
          </div>
        ))}
      </div>

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
        {busy ? "Taranıyor…" : "Taramayı başlat"}
      </button>
    </form>
  );
}
