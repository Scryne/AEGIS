"use client";

// Olumsuz haber (E2.5 beta, ADR-0013): haber adaylarını toplar, insan "ilgili / ilgisiz" der.
//
// Adaylar risk puanına girmez; "ilgili" kararı gerekçe ister ve denetim izine yazılır. Başlıktaki
// olumsuz terimler yalnız sıralama ipucudur: haberin bu kişi/şirket hakkında olup olmadığını
// insan karar verir (aynı adlı başka biri olabilir).

import { useRouter } from "next/navigation";
import { useState } from "react";

export interface AdverseMediaItem {
  id: string;
  title: string;
  url: string;
  source_name: string;
  published_at: string | null;
  negative_terms: string[];
  status: "aday" | "ilgili" | "ilgisiz";
  review_note: string | null;
  reviewed_at: string | null;
}

export interface AdverseMediaList {
  enabled: boolean;
  items: AdverseMediaItem[];
  counts: Record<string, number>;
}

const SEKMELER: { key: AdverseMediaItem["status"]; label: string }[] = [
  { key: "aday", label: "İncelenecek" },
  { key: "ilgili", label: "İlgili" },
  { key: "ilgisiz", label: "İlgisiz" },
];

function Karar({ item, onDone }: { item: AdverseMediaItem; onDone: () => void }) {
  const [not, setNot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function karar(decision: "ilgili" | "ilgisiz") {
    if (not.trim().length < 10) {
      setError("Gerekçe en az 10 karakter olmalı: kim, neden ilgili/ilgisiz.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/adverse-media/${item.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, note: not.trim() }),
      });
      if (!res.ok) {
        setError("Karar kaydedilemedi. Sayfayı yenileyip tekrar deneyin.");
        return;
      }
      onDone();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <label className="block text-xs text-muted" htmlFor={`not-${item.id}`}>
        Gerekçe
      </label>
      <textarea
        id={`not-${item.id}`}
        rows={2}
        maxLength={2000}
        value={not}
        onChange={(e) => setNot(e.target.value)}
        placeholder="Ör. Haberdeki kişi şirketin genel müdürü; adı ve görevi birebir geçiyor."
        className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
      />
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => karar("ilgili")}
          className="rounded-md border border-danger px-3 py-1.5 text-xs font-medium text-danger disabled:opacity-60"
        >
          İlgili: dosyaya bağla
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => karar("ilgisiz")}
          className="rounded-md border border-border px-3 py-1.5 text-xs text-fg disabled:opacity-60"
        >
          İlgisiz: başka kişi/olay
        </button>
      </div>
    </div>
  );
}

export function AdverseMediaPanel({
  entityId,
  data,
  canWrite,
}: {
  entityId: string;
  data: AdverseMediaList;
  canWrite: boolean;
}) {
  const router = useRouter();
  const [sekme, setSekme] = useState<AdverseMediaItem["status"]>("aday");
  const [busy, setBusy] = useState(false);
  const [mesaj, setMesaj] = useState<{ tur: "ok" | "hata"; metin: string } | null>(null);

  async function tara() {
    setBusy(true);
    setMesaj(null);
    try {
      const res = await fetch(`/api/v1/entities/${entityId}/adverse-media/scan`, { method: "POST" });
      const body = (await res.json().catch(() => null)) as
        | { new?: number; fetched?: number; failed_queries?: string[]; error?: { message: string } }
        | null;
      if (!res.ok) {
        setMesaj({ tur: "hata", metin: body?.error?.message ?? "Haber taraması yapılamadı." });
        return;
      }
      const eksik = body?.failed_queries?.length ? " Bir sorgu kaynağa ulaşamadı." : "";
      const metin =
        (body?.fetched ?? 0) === 0
          ? `Bu adla haber bulunamadı.${eksik}`
          : `${body?.fetched} sonuç tarandı, ${body?.new ?? 0} yeni aday eklendi.${eksik}`;
      setMesaj({ tur: "ok", metin });
      router.refresh();
    } catch {
      setMesaj({ tur: "hata", metin: "Sunucuya ulaşılamadı." });
    } finally {
      setBusy(false);
    }
  }

  const liste = data.items.filter((i) => i.status === sekme);

  return (
    <section aria-labelledby="haber-baslik" className="space-y-4 rounded-card border border-border bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="haber-baslik" className="text-sm font-semibold text-fg">
            Olumsuz haber <span className="ml-1 rounded-full border border-warning px-2 py-0.5 text-xs font-normal text-warning">beta</span>
          </h2>
          <p className="mt-1 max-w-prose text-xs text-muted">
            Türkçe haber başlıkları adla aranır. Adaylar risk puanına girmez; yalnız sizin
            &quot;ilgili&quot; dediğiniz haber dosyaya bağlanır.
          </p>
        </div>
        {data.enabled && canWrite && (
          <button
            type="button"
            onClick={tara}
            disabled={busy}
            className="rounded-md border border-primary px-3 py-1.5 text-sm font-medium text-primary disabled:opacity-60"
          >
            {busy ? "Taranıyor…" : "Haberleri tara"}
          </button>
        )}
      </div>

      {!data.enabled ? (
        <p className="rounded-md border border-border bg-bg p-3 text-sm text-muted">
          Beta bu hesapta kapalı. Hesap sahibi &quot;Plan ve Kullanım&quot; sayfasından açabilir.
        </p>
      ) : (
        <>
          {mesaj && (
            <p role={mesaj.tur === "hata" ? "alert" : "status"} className={`text-sm ${mesaj.tur === "hata" ? "text-danger" : "text-fg"}`}>
              {mesaj.metin}
            </p>
          )}
          <nav aria-label="Aday durumu" className="flex flex-wrap gap-1">
            {SEKMELER.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setSekme(s.key)}
                aria-pressed={sekme === s.key}
                className={`rounded-md px-3 py-1.5 text-sm ${
                  sekme === s.key ? "bg-bg font-medium text-primary shadow-sm" : "text-muted hover:text-fg"
                }`}
              >
                {s.label} ({data.counts[s.key] ?? 0})
              </button>
            ))}
          </nav>
          {liste.length === 0 ? (
            <p className="text-sm text-muted">
              {sekme === "aday" ? "İncelenecek aday yok. Haberleri tarayarak başlayın." : "Bu durumda haber yok."}
            </p>
          ) : (
            <ul className="space-y-3">
              {liste.map((item) => (
                <li key={item.id} className="space-y-2 rounded-md border border-border p-4">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="block text-sm font-medium break-words text-fg underline"
                  >
                    {item.title}
                  </a>
                  <p className="text-xs text-muted">
                    {item.source_name || "Kaynak belirtilmemiş"}
                    {item.published_at && ` · ${new Date(item.published_at).toLocaleDateString("tr-TR")}`}
                  </p>
                  {item.negative_terms.length > 0 && (
                    <ul aria-label="Başlıkta geçen olumsuz terimler" className="flex flex-wrap gap-1">
                      {item.negative_terms.map((t) => (
                        <li key={t} className="rounded-full border border-warning px-2 py-0.5 text-xs text-warning">
                          {t}
                        </li>
                      ))}
                    </ul>
                  )}
                  {item.status !== "aday" && item.review_note && (
                    <p className="text-xs text-muted">Gerekçe: {item.review_note}</p>
                  )}
                  {item.status === "aday" && canWrite && <Karar item={item} onDone={() => router.refresh()} />}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
