// Denetim izi görüntüleyici (E1.5) — salt-okunur: kim, ne, ne zaman, neye dayanarak.
//
// Sayfa hiçbir rol için yazma sunmaz; denetim izi append-only'dir (Invariant 2) ve
// veritabanı düzeyinde de değiştirilemez. Üstteki rozet, kiracının hash zincirinin
// kurcalanmadığını doğrular — "iz var" ile "iz bozulmamış" ayrı iddialardır.

import Link from "next/link";

import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";
import type { AuditEventPage, ChainVerification } from "@/lib/reports";
import { actionLabel, objectTypeLabel } from "@/lib/reports";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;

async function safeJson<T>(path: string): Promise<T | null> {
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as T;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("tr-TR");
}

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ action?: string; offset?: string }>;
}) {
  const user = await getCurrentUser();
  const params = await searchParams;
  const offset = Number.parseInt(params.offset ?? "0", 10) || 0;

  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (params.action) query.set("action", params.action);

  const [page, chain] = await Promise.all([
    safeJson<AuditEventPage>(`/audit/events?${query.toString()}`),
    safeJson<ChainVerification>("/audit/verify"),
  ]);

  if (page === null) {
    return (
      <div className="mx-auto max-w-5xl">
        <h1 className="text-2xl font-semibold text-fg">Denetim İzi</h1>
        <p className="mt-2 text-sm text-danger">
          Denetim izi görüntülenemedi. Bu sayfa yalnızca sahip, uyum uzmanı ve denetçi
          rollerine açıktır.
        </p>
      </div>
    );
  }

  const shown = page.items.length;
  const hasPrev = offset > 0;
  const hasNext = offset + shown < page.total;
  const linkFor = (nextOffset: number) => {
    const next = new URLSearchParams();
    if (params.action) next.set("action", params.action);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    const suffix = next.toString();
    return suffix ? `/audit?${suffix}` : "/audit";
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Denetim İzi</h1>
        <p className="text-sm text-muted">
          Risk etkileyen her eylem tam olarak bir olay yazar. Kayıtlar değiştirilemez;
          {user.role === "auditor" && " denetçi rolü salt-okunurdur ve"} bu sayfada hiçbir
          rol düzenleme yapamaz.
        </p>
      </div>

      {/* Zincir bütünlüğü: trigger'ı aşan bir müdahale bile burada yakalanır. */}
      {chain !== null && (
        <div
          className={`rounded-card border bg-surface p-4 text-sm ${
            chain.ok ? "border-success text-success" : "border-danger text-danger"
          }`}
        >
          {chain.ok ? (
            <>
              <strong className="font-semibold">Zincir bütünlüğü doğrulandı.</strong>{" "}
              {chain.events_checked} olay baştan yeniden hesaplandı; kurcalama izi yok.
            </>
          ) : (
            <>
              <strong className="font-semibold">Zincir bütünlüğü BOZUK.</strong> Kopuş{" "}
              {chain.broken_seq}. sırada ({chain.reason}). Bu bulgu derhal
              incelenmelidir.
            </>
          )}
        </div>
      )}

      <div className="rounded-card border border-border bg-surface p-5">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">
            Olaylar
          </h2>
          <span className="text-xs text-muted">
            {page.total} kayıt · {offset + 1}–{offset + shown} arası
          </span>
        </div>

        {shown === 0 ? (
          <p className="text-sm text-muted">Kayıt yok.</p>
        ) : (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-muted">
                <th className="pb-2 font-medium">Sıra</th>
                <th className="pb-2 font-medium">Zaman</th>
                <th className="pb-2 font-medium">Kim</th>
                <th className="pb-2 font-medium">Ne</th>
                <th className="pb-2 font-medium">Hedef</th>
                <th className="pb-2 font-medium">Neye dayanarak</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {page.items.map((event) => (
                <tr key={event.id}>
                  <td className="py-1.5 font-mono text-muted">{event.seq}</td>
                  <td className="py-1.5 text-muted">{formatDate(event.occurred_at)}</td>
                  <td className="py-1.5 text-fg">
                    {event.actor_label ?? event.actor_user_id ?? "sistem"}
                    {event.actor_role !== null && (
                      <span className="block text-[10px] text-muted">{event.actor_role}</span>
                    )}
                  </td>
                  <td className="py-1.5 text-fg">{actionLabel(event.action)}</td>
                  <td className="py-1.5 text-muted">
                    {objectTypeLabel(event.object_type)}
                    {event.object_id !== null && (
                      <span className="block font-mono text-[10px]">{event.object_id}</span>
                    )}
                  </td>
                  <td className="py-1.5 break-all text-muted">{event.source_ref ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {(hasPrev || hasNext) && (
          <div className="mt-4 flex gap-3 text-sm">
            {hasPrev && (
              <Link href={linkFor(Math.max(0, offset - PAGE_SIZE))} className="text-fg underline">
                ← Önceki
              </Link>
            )}
            {hasNext && (
              <Link href={linkFor(offset + PAGE_SIZE)} className="text-fg underline">
                Sonraki →
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
