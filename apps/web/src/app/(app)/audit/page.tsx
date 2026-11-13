// Denetim izi görüntüleyici (E1.5) — salt-okunur: kim, ne, ne zaman, neye dayanarak.
//
// Sayfa hiçbir rol için yazma sunmaz; denetim izi append-only'dir (Invariant 2) ve
// veritabanı düzeyinde de değiştirilemez. Üstteki rozet, kiracının hash zincirinin
// kurcalanmadığını doğrular — "iz var" ile "iz bozulmamış" ayrı iddialardır.

import Link from "next/link";

import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";
import type { AuditEventPage, ChainVerification } from "@/lib/reports";
import { ACTION_LABELS, actionLabel, actorRoleLabel, objectTypeLabel } from "@/lib/reports";

export const metadata = { title: "Denetim İzi" };

export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;

async function safeJson<T>(path: string): Promise<T | null> {
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as T;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("tr-TR", {
    timeZone: "Europe/Istanbul",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
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
      <div className="page">
        <h1 className="page-title">Denetim İzi</h1>
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
    <div className="page space-y-5">
      <div>
        <h1 className="page-title">Denetim İzi</h1>
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
            chain.ok ? "border-success/40 bg-success-soft text-success" : "border-danger/40 bg-danger-soft text-danger"
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

      <div className="panel p-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="eyebrow">Olaylar</h2>
            <p className="mt-1 text-xs text-muted">
              <span className="font-mono tabular-nums">{page.total}</span> kayıt
              {shown > 0 && (
                <>
                  {" "}
                  · <span className="font-mono tabular-nums">{offset + 1}–{offset + shown}</span> arası
                </>
              )}
              {params.action && <> · süzgeç: {actionLabel(params.action)}</>}
            </p>
          </div>
          <form method="get" className="flex flex-wrap items-end gap-2">
            <label className="space-y-1 text-xs text-muted">
              <span className="block">Eylem</span>
              <select name="action" defaultValue={params.action ?? ""} className="field w-auto max-w-full">
                <option value="">Tüm eylemler</option>
                {Object.entries(ACTION_LABELS)
                  .sort(([, a], [, b]) => a.localeCompare(b, "tr"))
                  .map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
              </select>
            </label>
            <button type="submit" className="btn-quiet">
              Süz
            </button>
            {params.action && (
              <Link href="/audit" className="btn-quiet">
                Temizle
              </Link>
            )}
          </form>
        </div>

        {shown === 0 ? (
          <p className="text-sm text-muted">
            {params.action ? "Bu eylem için kayıt yok." : "Henüz denetim olayı yok."}
          </p>
        ) : (
          <ol className="divide-y divide-border text-xs" aria-label="Denetim olayları">
            <li
              aria-hidden="true"
              className="hidden pb-2 font-medium text-muted lg:grid lg:grid-cols-[3.5rem_9.5rem_10rem_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-3"
            >
              <span>Sıra</span>
              <span>Zaman</span>
              <span>Kim</span>
              <span>Ne</span>
              <span>Hedef</span>
              <span>Neye dayanarak</span>
            </li>
            {page.items.map((event) => (
              <li
                key={event.id}
                className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 py-2.5 lg:grid-cols-[3.5rem_9.5rem_10rem_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)] lg:items-start"
              >
                <span className="font-mono text-muted tabular-nums">#{event.seq}</span>
                <span className="font-mono whitespace-nowrap text-muted tabular-nums">
                  {formatDate(event.occurred_at)}
                </span>
                <span className="col-span-2 text-fg lg:col-span-1">
                  {event.actor_label ?? (event.actor_user_id ? "Kullanıcı" : "Sistem")}
                  {event.actor_role !== null && (
                    <span className="ml-1.5 text-muted lg:ml-0 lg:block">{actorRoleLabel(event.actor_role)}</span>
                  )}
                </span>
                <span className="col-span-2 text-sm font-medium text-fg lg:col-span-1 lg:text-xs lg:font-normal">
                  {actionLabel(event.action)}
                </span>
                <span className="col-span-2 min-w-0 text-muted lg:col-span-1">
                  {objectTypeLabel(event.object_type)}
                  {event.object_id !== null && (
                    <span className="ml-1.5 font-mono text-[11px] break-all lg:ml-0 lg:block">{event.object_id}</span>
                  )}
                </span>
                <span className="col-span-2 min-w-0 font-mono text-[11px] break-all text-muted lg:col-span-1">
                  {event.source_ref ? (
                    <>
                      <span className="font-sans text-xs lg:hidden">Dayanak: </span>
                      {event.source_ref}
                    </>
                  ) : (
                    <span className="hidden lg:inline">—</span>
                  )}
                </span>
              </li>
            ))}
          </ol>
        )}

        {(hasPrev || hasNext) && (
          <nav aria-label="Sayfalar" className="mt-4 flex gap-3 text-sm">
            {hasPrev && (
              <Link href={linkFor(Math.max(0, offset - PAGE_SIZE))} className="btn-quiet">
                ← Önceki
              </Link>
            )}
            {hasNext && (
              <Link href={linkFor(offset + PAGE_SIZE)} className="btn-quiet">
                Sonraki →
              </Link>
            )}
          </nav>
        )}
      </div>
    </div>
  );
}
