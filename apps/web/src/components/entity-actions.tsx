"use client";

// Varlık eylemleri: kütükten doğrudan tarama ve GLEIF zenginleştirmesi.
//
// Tarama, dosyada kayıtlı kişilerle birlikte koşar (şirket + yönetici/UBO) — kullanıcı
// adları yeniden yazmaz. Motor erişilemezse (502) yine bir kayıt oluşur ve kullanıcı
// "tarama yapılamadı" uyarısını görmek üzere o kayda yönlendirilir.

import { useRouter } from "next/navigation";
import { useState } from "react";

export function EntityActions({ entityId, hasLei }: { entityId: string; hasLei: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function screen() {
    setBusy("screen");
    setError(null);
    setMessage(null);
    try {
      const res = await fetch(`/api/v1/screenings/from-entity/${entityId}`, { method: "POST" });
      const payload = (await res.json().catch(() => null)) as
        | { id?: string; error?: { message?: string } }
        | null;
      if (res.ok || (res.status === 502 && payload?.id)) {
        router.push(`/screenings/${payload?.id}`);
        return;
      }
      setError(payload?.error?.message ?? "Tarama başlatılamadı.");
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(null);
    }
  }

  async function enrich() {
    setBusy("gleif");
    setError(null);
    setMessage(null);
    try {
      const res = await fetch(`/api/v1/entities/${entityId}/enrich/gleif`, { method: "POST" });
      const payload = (await res.json().catch(() => null)) as
        | { legal_name?: string; discrepancies_created?: number; error?: { message?: string } }
        | null;
      if (!res.ok) {
        setError(payload?.error?.message ?? "GLEIF sorgusu başarısız.");
        return;
      }
      const farklar = payload?.discrepancies_created ?? 0;
      setMessage(
        farklar > 0
          ? `GLEIF kaydı alındı; ${farklar} tutarsızlık bulundu.`
          : "GLEIF kaydı alındı; beyanla çelişki yok.",
      );
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
          onClick={screen}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-fg disabled:opacity-50"
        >
          {busy === "screen" ? "Taranıyor…" : "Dosyayı tara"}
        </button>
        {hasLei && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={enrich}
            className="rounded-md border border-border px-3 py-1.5 text-sm text-fg disabled:opacity-50"
          >
            {busy === "gleif" ? "Sorgulanıyor…" : "GLEIF ile doğrula"}
          </button>
        )}
      </div>
      {message !== null && <p className="text-sm text-success">{message}</p>}
      {error !== null && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
