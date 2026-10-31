"use client";

// Varlık sayfasından ŞİB taslağı açma (E2.2). Taslak dosyadan ön doldurulur; açılış denetim
// izine yazılır. Yalnız sahip ve uyum görevlisine gösterilir (sayfa + backend kapısı).

import { useRouter } from "next/navigation";
import { useState } from "react";

export function SibCreate({ entityId }: { entityId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/entities/${entityId}/sib-drafts`, { method: "POST" });
      const body = (await res.json().catch(() => null)) as { id?: string; error?: { message?: string } } | null;
      if (!res.ok || !body?.id) {
        setError(body?.error?.message ?? "Taslak açılamadı.");
        return;
      }
      router.push(`/sib/${body.id}`);
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={create}
        disabled={busy}
        className="rounded-md border border-danger px-3 py-1.5 text-sm font-medium text-danger disabled:opacity-50"
      >
        {busy ? "Hazırlanıyor…" : "ŞİB taslağı hazırla"}
      </button>
      <p className="text-xs text-muted">
        Kimlik, gerçek faydalanıcı ve risk bulguları dosyadan aktarılır; kategori ve açıklama sizin
        kararınızdır.
      </p>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
