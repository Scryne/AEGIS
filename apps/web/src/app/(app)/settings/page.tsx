// Ayarlar: kiracının tarama eşik bandı (sahip ve uyum uzmanı değiştirir, gerekçesi denetim izine
// girer), ekip ve rolleri, kendi ekranı olan ayarlara yönlendirme. Okuma bütün rollere açıktır;
// yazma yetkisi API'de (RequireSettingsWrite) ayrıca kapılıdır.

import Link from "next/link";

import { TeamManager, type TeamMember } from "@/components/team-manager";
import { ThresholdSettings, type Thresholds } from "@/components/threshold-settings";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser, ROLE_LABELS, type Role } from "@/lib/server/user";

export const metadata = { title: "Ayarlar" };

export const dynamic = "force-dynamic";

const THRESHOLD_KEY = "screening.thresholds";
// Motor varsayılanı (aegis_core.screening.thresholds.ScreeningThresholds); kiracı ayarı yoksa geçerlidir.
const DEFAULTS: Thresholds = { candidate_cutoff: 0.5, auto_dismiss_below: 0.65, auto_flag_at: 0.85 };

interface Setting {
  key: string;
  value: Record<string, unknown>;
}

type Member = TeamMember;

interface AuditEvent {
  id: string;
  seq: number;
  actor_label: string | null;
  actor_role: string | null;
  payload: { value?: Partial<Thresholds>; note?: string };
  occurred_at: string;
  object_id: string | null;
}

async function safeJson<T>(path: string): Promise<T | null> {
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as T;
}

const ROLE_ORDER: Role[] = ["owner", "compliance_officer", "analyst", "auditor"];

function formatDate(value: string): string {
  return new Date(value).toLocaleString("tr-TR", {
    timeZone: "Europe/Istanbul",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

const band = (v?: Partial<Thresholds>) =>
  v
    ? [v.candidate_cutoff, v.auto_dismiss_below, v.auto_flag_at]
        .map((x) => (typeof x === "number" ? x.toFixed(2).replace(".", ",") : "—"))
        .join(" · ")
    : "—";

export default async function SettingsPage() {
  const user = await getCurrentUser();
  const canEdit = user.role === "owner" || user.role === "compliance_officer";
  const canReadAudit = user.role !== "analyst";

  const [settings, members, history] = await Promise.all([
    safeJson<Setting[]>("/settings"),
    safeJson<Member[]>("/members"),
    canReadAudit
      ? safeJson<{ items: AuditEvent[] }>(
          `/audit/events?${new URLSearchParams({ action: "tenant_setting.update", object_id: THRESHOLD_KEY, limit: "8" })}`,
        )
      : Promise.resolve(null),
  ]);

  const stored = settings?.find((s) => s.key === THRESHOLD_KEY)?.value as Partial<Thresholds> | undefined;
  const thresholds: Thresholds = { ...DEFAULTS, ...stored };
  const sortedMembers = [...(members ?? [])].sort(
    (a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || a.email.localeCompare(b.email, "tr"),
  );

  const elsewhere: { href: string; title: string; text: string; roles: Role[] }[] = [
    {
      href: "/monitoring",
      title: "İzleme bildirimleri",
      text: "Derece başına hemen ya da günlük özet e-postası ve alıcı roller.",
      roles: ROLE_ORDER,
    },
    {
      href: "/plan",
      title: "Olumsuz haber (beta)",
      text: "Kiracı için açma ve kapatma; yalnız sahip değiştirir.",
      roles: ["owner", "compliance_officer", "auditor"],
    },
    {
      href: "/integrations",
      title: "API anahtarları ve webhook",
      text: "Kendi sisteminizi bağlamak için rol kapsamlı anahtarlar ve olay bildirimleri.",
      roles: ["owner", "compliance_officer", "auditor"],
    },
  ];

  return (
    <div className="page space-y-6">
      <div>
        <h1 className="page-title">Ayarlar</h1>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Kurumunuzun tarama davranışı ve ekibi. Her değişiklik kimin, ne zaman ve hangi gerekçeyle yaptığıyla
          denetim izine yazılır.
        </p>
      </div>

      <section aria-labelledby="esik-baslik" className="panel space-y-5 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="esik-baslik" className="eyebrow">
              Tarama eşik bandı
            </h2>
            <p className="mt-1 max-w-prose text-xs text-muted">
              Eşleşme skoru adayın hangi kuyruğa düşeceğini belirler. Bant yalnız sonraki taramaları etkiler;
              geçmiş taramalar kendi bantlarıyla kayıtlıdır.{" "}
              {stored ? "Kurumunuza özel bant geçerli." : "Şu an motor varsayılanı geçerli."}
            </p>
          </div>
          {canReadAudit && (
            <Link href="/quality" className="btn-quiet">
              Kalite ölçümüne bak
            </Link>
          )}
        </div>
        <ThresholdSettings initial={thresholds} canEdit={canEdit} />
        {!canEdit && (
          <p className="text-xs text-muted">
            Eşik bandını sahip ve uyum uzmanı değiştirir; rolünüz ({ROLE_LABELS[user.role]}) bu ayarı yalnız
            görür.
          </p>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="ekip-baslik" className="panel p-5">
          <h2 id="ekip-baslik" className="eyebrow">
            Ekip
          </h2>
          {members === null ? (
            <p role="alert" className="mt-3 text-sm text-danger">
              Ekip listesi yüklenemedi. Sayfayı yenileyin; sürerse sunucu kaydına bakın.
            </p>
          ) : (
            <TeamManager members={sortedMembers} currentUserId={user.id} canManage={user.role === "owner"} />
          )}
        </section>

        <section aria-labelledby="diger-baslik" className="panel p-5">
          <h2 id="diger-baslik" className="eyebrow">
            Kendi ekranı olan ayarlar
          </h2>
          <ul className="mt-3 divide-y divide-border">
            {elsewhere
              .filter((e) => e.roles.includes(user.role))
              .map((e) => (
                <li key={e.href}>
                  <Link href={e.href} className="row-link -mx-2 rounded-md px-2 py-2.5">
                    <span className="block text-sm font-medium text-primary">{e.title} →</span>
                    <span className="mt-0.5 block text-xs text-muted">{e.text}</span>
                  </Link>
                </li>
              ))}
          </ul>
        </section>
      </div>

      {canReadAudit && (
        <section aria-labelledby="gecmis-baslik" className="panel p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="gecmis-baslik" className="eyebrow">
              Eşik değişiklikleri
            </h2>
            <Link
              href="/audit?action=tenant_setting.update"
              className="inline-flex min-h-8 items-center text-xs text-primary hover:underline"
            >
              Denetim izinde aç
            </Link>
          </div>
          {history === null ? (
            <p role="alert" className="mt-3 text-sm text-danger">
              Değişiklik geçmişi yüklenemedi.
            </p>
          ) : history.items.length === 0 ? (
            <p className="mt-3 text-sm text-muted">Eşik bandı hiç değiştirilmedi; motor varsayılanı kullanılıyor.</p>
          ) : (
            <ol className="mt-3 divide-y divide-border">
              {history.items.map((e) => (
                <li key={e.id} className="grid gap-1 py-2.5 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4">
                  <div className="font-mono text-xs text-muted tabular-nums">
                    #{e.seq} · {formatDate(e.occurred_at)}
                  </div>
                  <div className="min-w-0 text-sm">
                    <div className="text-fg">
                      <span className="font-mono tabular-nums">{band(e.payload.value)}</span>
                      <span className="text-muted"> · {e.actor_label ?? "sistem"}</span>
                    </div>
                    <div className="mt-0.5 text-xs break-words text-muted">
                      {e.payload.note ?? "Gerekçe yazılmamış (gerekçe zorunluluğundan önceki kayıt)."}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-3 text-xs text-muted">Sıra: alt sınır · eleme · işaretleme.</p>
        </section>
      )}
    </div>
  );
}
