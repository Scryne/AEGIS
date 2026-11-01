// Entegrasyonlar (E3.4): kendi sisteminizi AEGIS'e bağlamak için API anahtarları ve webhook'lar.
// Anahtarı yalnız sahip açar/iptal eder; webhook'u sahip ve uyum uzmanı yönetir; denetçi okur.

import { ApiKeyCreate, ApiKeyRevoke, Redeliver, WebhookActions, WebhookCreate } from "@/components/integration-controls";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";

export const dynamic = "force-dynamic";

interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  role: "analyst" | "auditor";
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

interface Webhook {
  id: string;
  url: string;
  description: string | null;
  events: string[];
  active: boolean;
  created_at: string;
}

interface Delivery {
  id: string;
  event: string;
  status: "pending" | "delivered" | "dead" | "skipped";
  attempts: number;
  next_attempt_at: string | null;
  last_status_code: number | null;
  last_error: string | null;
  delivered_at: string | null;
  created_at: string;
}

const ROLE = { analyst: "Analist", auditor: "Denetçi" } as const;
const DELIVERY = {
  pending: { label: "Bekliyor", tone: "border-border text-muted" },
  delivered: { label: "Teslim edildi", tone: "border-success text-fg" },
  dead: { label: "Teslim edilemedi", tone: "border-danger text-danger" },
  skipped: { label: "Atlandı", tone: "border-border text-muted" },
} as const;

function when(v: string | null): string {
  return v ? new Date(v).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" }) : "—";
}

async function json<T>(path: string): Promise<T | null> {
  const res = await serverFetch(path);
  return res.ok ? ((await res.json()) as T) : null;
}

export default async function IntegrationsPage() {
  const user = await getCurrentUser();
  const isOwner = user.role === "owner";
  const canManageHooks = isOwner || user.role === "compliance_officer";
  const canRead = canManageHooks || user.role === "auditor";

  if (!canRead) {
    return (
      <div className="mx-auto max-w-4xl">
        <h1 className="text-2xl font-semibold text-fg">Entegrasyonlar</h1>
        <p className="mt-2 text-sm text-muted">Bu sayfa sahip, uyum uzmanı ve denetçiye açıktır.</p>
      </div>
    );
  }

  const [keys, hooks, catalog] = await Promise.all([
    json<ApiKey[]>("/api-keys"),
    json<Webhook[]>("/webhooks"),
    json<{ events: string[] }>("/webhooks/events"),
  ]);
  const logs = await Promise.all(
    (hooks ?? []).map((h) => json<Delivery[]>(`/webhooks/${h.id}/deliveries?limit=10`)),
  );

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Entegrasyonlar</h1>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Kendi sisteminizden tarama başlatmak için API anahtarı, sonuçları beklemeden almak için
          webhook kullanın. Olaylar kişisel veri taşımaz; ayrıntıyı API&apos;den kimlikle çekersiniz.
          Kurulum adımları ve imza doğrulama örnekleri API belgesindedir (docs/api).
        </p>
      </div>

      <section aria-labelledby="anahtar-baslik" className="space-y-4 rounded-card border border-border bg-surface p-5">
        <div>
          <h2 id="anahtar-baslik" className="text-sm font-semibold tracking-wide text-muted uppercase">
            API anahtarları
          </h2>
          <p className="mt-1 text-xs text-muted">
            Anahtar, seçilen rolün yetkisiyle çalışır. Eşleşme onayı ve vaka kararı anahtarla verilemez.
            Dakikada 120 istek.
          </p>
        </div>
        {isOwner && <ApiKeyCreate />}
        {keys === null ? (
          <p role="alert" className="text-sm text-danger">Anahtarlar yüklenemedi.</p>
        ) : keys.length === 0 ? (
          <p className="text-sm text-muted">Henüz anahtar yok.</p>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {keys.map((k) => (
              <li key={k.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                <div className="min-w-0">
                  <p className={`text-sm font-medium ${k.revoked_at ? "text-muted line-through" : "text-fg"}`}>
                    {k.name}
                  </p>
                  <p className="text-xs text-muted">
                    <span className="font-mono">aeg_{k.prefix}_…</span> · {ROLE[k.role]} · açıldı {when(k.created_at)} ·
                    son kullanım {when(k.last_used_at)}
                    {k.expires_at && ` · bitiş ${when(k.expires_at)}`}
                    {k.revoked_at && ` · iptal ${when(k.revoked_at)}`}
                  </p>
                </div>
                {isOwner && !k.revoked_at && <ApiKeyRevoke keyId={k.id} name={k.name} />}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="webhook-baslik" className="space-y-4 rounded-card border border-border bg-surface p-5">
        <div>
          <h2 id="webhook-baslik" className="text-sm font-semibold tracking-wide text-muted uppercase">
            Webhook&apos;lar
          </h2>
          <p className="mt-1 text-xs text-muted">
            Her istek HMAC-SHA256 ile imzalanır (X-Aegis-Signature). Başarısız teslim 30 sn, 2 dk, 10 dk, 1 sa ve
            6 sa sonra yeniden denenir. İç ağ adreslerine gönderim yapılmaz.
          </p>
        </div>
        {canManageHooks && catalog && <WebhookCreate events={catalog.events} />}
        {hooks === null ? (
          <p role="alert" className="text-sm text-danger">Webhook&apos;lar yüklenemedi.</p>
        ) : hooks.length === 0 ? (
          <p className="text-sm text-muted">Henüz webhook yok.</p>
        ) : (
          <ul className="space-y-4">
            {hooks.map((h, i) => (
              <li key={h.id} className="space-y-3 rounded-md border border-border p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-mono text-sm break-all text-fg">{h.url}</p>
                    <p className="mt-1 text-xs text-muted">
                      {h.active ? "Etkin" : "Durduruldu"} · {h.events.join(", ")}
                    </p>
                  </div>
                  {canManageHooks && <WebhookActions id={h.id} active={h.active} />}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[34rem] text-left text-xs">
                    <caption className="sr-only">Son teslimler</caption>
                    <thead className="text-muted">
                      <tr>
                        <th className="py-1 pr-3 font-medium">Olay</th>
                        <th className="py-1 pr-3 font-medium">Durum</th>
                        <th className="py-1 pr-3 font-medium">Deneme</th>
                        <th className="py-1 pr-3 font-medium">Son yanıt</th>
                        <th className="py-1 pr-3 font-medium">Zaman</th>
                        <th className="py-1 font-medium">
                          <span className="sr-only">Eylem</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {(logs[i] ?? []).length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-2 text-muted">
                            Henüz teslim yok.
                          </td>
                        </tr>
                      ) : (
                        (logs[i] ?? []).map((d) => (
                          <tr key={d.id}>
                            <td className="py-1.5 pr-3 font-mono text-fg">{d.event}</td>
                            <td className="py-1.5 pr-3">
                              <span className={`rounded-full border px-2 py-0.5 ${DELIVERY[d.status].tone}`}>
                                {DELIVERY[d.status].label}
                              </span>
                            </td>
                            <td className="py-1.5 pr-3 font-mono tabular-nums">{d.attempts}</td>
                            <td className="py-1.5 pr-3 text-muted">
                              {d.last_status_code ?? "—"}
                              {d.last_error && ` · ${d.last_error}`}
                            </td>
                            <td className="py-1.5 pr-3 text-muted">
                              {d.status === "pending" && d.next_attempt_at
                                ? `sonraki ${when(d.next_attempt_at)}`
                                : when(d.delivered_at ?? d.created_at)}
                            </td>
                            <td className="py-1.5">
                              {canManageHooks && (d.status === "dead" || d.status === "skipped") && (
                                <Redeliver deliveryId={d.id} />
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
