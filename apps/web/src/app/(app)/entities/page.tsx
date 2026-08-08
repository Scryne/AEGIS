// Varlıklar — kütük listesi, arama ve yeni kayıt.

import Link from "next/link";

import { EntityForm } from "@/components/entity-form";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";
import type { Discrepancy, EntityList } from "@/lib/entities";

export const dynamic = "force-dynamic";

async function safeJson<T>(path: string): Promise<T | null> {
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as T;
}

export default async function EntitiesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const user = await getCurrentUser();
  const query = q?.trim() ?? "";
  const [list, discrepancies] = await Promise.all([
    safeJson<EntityList>(`/entities${query ? `?q=${encodeURIComponent(query)}` : ""}`),
    safeJson<Discrepancy[]>("/entities/discrepancies?open_only=true"),
  ]);
  const canWrite = user.role !== "auditor";
  const openDiscrepancies = discrepancies ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Varlıklar</h1>
        <p className="text-sm text-muted">
          Şirket ve kişi kayıtları; belgeler, bağlar ve kaynak referansları.
        </p>
      </div>

      {/* Açık tutarsızlık, dosyanın "hazır" görünmesini engelleyen bir bulgudur —
          listeden önce gösterilir. */}
      {openDiscrepancies.length > 0 && (
        <Link
          href={`/entities/${openDiscrepancies[0].entity_id}`}
          className="block rounded-card border border-warning bg-surface p-4 text-sm text-warning"
        >
          <strong className="font-semibold">
            {openDiscrepancies.length} açık tutarsızlık var.
          </strong>{" "}
          Beyan ile belge/kütük verisi çelişen dosyalar inceleme bekliyor.
        </Link>
      )}

      <section className="rounded-card border border-border bg-surface p-5">
        <form method="get" className="flex gap-2">
          <input
            name="q"
            defaultValue={query}
            placeholder="Unvan ya da ad ile ara…"
            className="flex-1 rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg"
          />
          <button
            type="submit"
            className="rounded-md border border-border px-3 py-2 text-sm text-fg"
          >
            Ara
          </button>
        </form>
      </section>

      {canWrite && (
        <section className="rounded-card border border-border bg-surface p-5">
          <h2 className="mb-4 text-sm font-semibold tracking-wide text-muted uppercase">
            Yeni kayıt
          </h2>
          <EntityForm />
        </section>
      )}

      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">
          Kayıtlı varlıklar {list !== null && `(${list.total})`}
        </h2>
        {list === null || list.items.length === 0 ? (
          <p className="text-sm text-muted">
            {query ? "Aramanıza uyan kayıt yok." : "Henüz kayıt yok."}
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {list.items.map((entity) => (
              <li key={entity.id} className="py-3">
                <Link href={`/entities/${entity.id}`} className="block hover:opacity-80">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-sm font-medium text-fg">{entity.name}</div>
                      <div className="mt-0.5 font-mono text-xs text-muted">
                        {entity.tax_number ?? entity.national_id_masked ?? "tanımlayıcı yok"}
                      </div>
                    </div>
                    <span className="shrink-0 rounded border border-border px-2 py-0.5 text-xs text-muted">
                      {entity.schema_type === "Person" ? "Gerçek kişi" : "Tüzel kişi"}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
