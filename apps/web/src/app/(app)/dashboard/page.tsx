import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";

interface Member {
  user_id: string;
  email: string;
  full_name: string | null;
  role: string;
}

interface Setting {
  key: string;
  value: Record<string, unknown>;
}

async function safeJson<T>(path: string): Promise<T | null> {
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as T;
}

export default async function DashboardPage() {
  const user = await getCurrentUser();
  const [members, settings] = await Promise.all([
    safeJson<Member[]>("/members"),
    safeJson<Setting[]>("/settings"),
  ]);
  const canWriteSettings = user.role === "owner" || user.role === "compliance_officer";

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Panel</h1>
        <p className="text-sm text-muted">
          Kiracı <span className="font-mono text-xs">{user.tenant_id}</span>
        </p>
      </div>

      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">Ofis üyeleri</h2>
        <ul className="divide-y divide-border">
          {(members ?? []).map((m) => (
            <li key={m.user_id} className="flex items-center justify-between py-2 text-sm">
              <span className="text-fg">{m.full_name ?? m.email}</span>
              <span className="text-muted">{m.role}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-card border border-border bg-surface p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">
            Kiracı ayarları
          </h2>
          <span className="text-xs text-muted">
            {canWriteSettings ? "Yazma yetkiniz var" : "Salt-okunur"}
          </span>
        </div>
        {settings === null || settings.length === 0 ? (
          <p className="text-sm text-muted">Henüz ayar yok.</p>
        ) : (
          <ul className="divide-y divide-border">
            {settings.map((s) => (
              <li key={s.key} className="flex items-center justify-between py-2 text-sm">
                <span className="font-mono text-fg">{s.key}</span>
                <span className="font-mono text-xs text-muted">{JSON.stringify(s.value)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
