// Varlık dosyası — kimlik, bağlar, belgeler, öneriler, tutarsızlıklar ve provenans.

import Link from "next/link";
import { notFound } from "next/navigation";

import { DiscrepancyReview } from "@/components/discrepancy-review";
import { DocumentUpload } from "@/components/document-upload";
import { EntityActions } from "@/components/entity-actions";
import { ProposalReview } from "@/components/proposal-review";
import { serverFetch } from "@/lib/server/backend";
import { getCurrentUser } from "@/lib/server/user";
import type {
  AegisDocument,
  Discrepancy,
  Entity,
  EntityAttribute,
  ExtractionProposal,
  Relationship,
} from "@/lib/entities";
import {
  DOC_TYPE_LABELS,
  EXTRACTION_STATUS_LABELS,
  REL_TYPE_LABELS,
  SOURCE_LABELS,
  attributeLabel,
} from "@/lib/entities";

export const dynamic = "force-dynamic";

async function safeJson<T>(path: string): Promise<T | null> {
  const res = await serverFetch(path);
  if (!res.ok) return null;
  return (await res.json()) as T;
}

function formatDate(value: string | null): string {
  return value === null ? "—" : new Date(value).toLocaleString("tr-TR");
}

export default async function EntityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const user = await getCurrentUser();

  const res = await serverFetch(`/entities/${id}`);
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error("Varlık yüklenemedi.");
  const entity = (await res.json()) as Entity;

  const [attributes, relationships, documents, discrepancies] = await Promise.all([
    safeJson<EntityAttribute[]>(`/entities/${id}/attributes`),
    safeJson<Relationship[]>(`/entities/${id}/relationships`),
    safeJson<AegisDocument[]>(`/documents?entity_id=${id}`),
    safeJson<Discrepancy[]>(`/entities/${id}/discrepancies`),
  ]);

  // Öneriler belge başına gelir; hepsini tek listede topluyoruz.
  const proposalLists = await Promise.all(
    (documents ?? []).map((document) =>
      safeJson<ExtractionProposal[]>(`/documents/${document.id}/proposals`),
    ),
  );
  const proposals = proposalLists.flatMap((list) => list ?? []);
  const pendingProposals = proposals.filter((item) => item.status === "pending");

  const canWrite = user.role !== "auditor";
  const canDecideDiscrepancy = user.role === "owner" || user.role === "compliance_officer";
  const openDiscrepancies = (discrepancies ?? []).filter((item) => item.status === "open");
  const closedDiscrepancies = (discrepancies ?? []).filter((item) => item.status !== "open");

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <Link href="/entities" className="text-xs text-muted hover:text-fg">
          ← Varlıklar
        </Link>
        <h1 className="mt-1 text-2xl font-semibold text-fg">{entity.name}</h1>
        <p className="text-sm text-muted">
          {entity.schema_type === "Person" ? "Gerçek kişi" : "Tüzel kişi"} ·{" "}
          <span className="font-mono">{entity.name_normalized}</span>
        </p>
      </div>

      {entity.status === "merged" && entity.merged_into_id !== null && (
        <div className="rounded-card border border-warning bg-surface p-4 text-sm text-warning">
          Bu kayıt başka bir kayda birleştirildi.{" "}
          <Link href={`/entities/${entity.merged_into_id}`} className="underline">
            Güncel kaydı aç
          </Link>
        </div>
      )}

      {openDiscrepancies.length > 0 && (
        <div className="rounded-card border border-danger bg-surface p-4 text-sm text-danger">
          <strong className="font-semibold">
            {openDiscrepancies.length} açık tutarsızlık.
          </strong>{" "}
          Beyan ile belge/kütük verisi çelişiyor; dosya kapatılmadan önce açıklanmalıdır.
        </div>
      )}

      {canWrite && (
        <section className="rounded-card border border-border bg-surface p-5">
          <EntityActions entityId={entity.id} hasLei={entity.lei_code !== null} />
        </section>
      )}

      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">Kimlik</h2>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          {[
            ["Vergi no", entity.tax_number],
            ["MERSİS no", entity.mersis_number],
            ["Ticaret sicil no", entity.trade_registry_number],
            ["LEI", entity.lei_code],
            ["T.C. kimlik no", entity.national_id_masked],
            ["Ülke", entity.country],
            ["Kuruluş tarihi", entity.incorporation_date],
            ["Doğum tarihi", entity.birth_date],
            ["Adres", entity.address],
          ]
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={String(label)}>
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="font-mono text-fg">{value}</dd>
              </div>
            ))}
        </dl>
      </section>

      {/* Bağlar — UBO HESABI Phase 2'dir; burada yalnız kayıtlı bağlar gösterilir. */}
      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">
          Bağlı kişiler ve şirketler
        </h2>
        {relationships === null || relationships.length === 0 ? (
          <p className="text-sm text-muted">Henüz bağ kaydedilmedi.</p>
        ) : (
          <ul className="divide-y divide-border">
            {relationships.map((relationship) => {
              const other =
                relationship.target_entity_id === entity.id
                  ? { id: relationship.source_entity_id, name: relationship.source_entity_name }
                  : { id: relationship.target_entity_id, name: relationship.target_entity_name };
              return (
                <li key={relationship.id} className="flex items-start justify-between gap-3 py-2">
                  <div>
                    <Link href={`/entities/${other.id}`} className="text-sm text-fg underline">
                      {other.name ?? "(adsız kayıt)"}
                    </Link>
                    <div className="text-xs text-muted">
                      {REL_TYPE_LABELS[relationship.rel_type] ?? relationship.rel_type}
                      {relationship.role_title !== null && ` — ${relationship.role_title}`}
                      {relationship.ownership_percent !== null &&
                        ` · %${relationship.ownership_percent}`}
                    </div>
                  </div>
                  <span className="shrink-0 rounded border border-border px-2 py-0.5 text-[10px] text-muted">
                    {SOURCE_LABELS[relationship.source_type] ?? relationship.source_type}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">Belgeler</h2>
        {documents === null || documents.length === 0 ? (
          <p className="text-sm text-muted">Henüz belge yüklenmedi.</p>
        ) : (
          <ul className="mb-4 divide-y divide-border">
            {documents.map((document) => (
              <li key={document.id} className="flex items-start justify-between gap-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-sm text-fg">{document.filename}</div>
                  <div className="text-xs text-muted">
                    {DOC_TYPE_LABELS[document.doc_type] ?? document.doc_type} ·{" "}
                    {formatDate(document.created_at)}
                    {document.source_ref !== null && ` · ${document.source_ref}`}
                  </div>
                  {document.extraction_error !== null && (
                    <div className="text-xs text-warning">{document.extraction_error}</div>
                  )}
                </div>
                <span className="shrink-0 rounded border border-border px-2 py-0.5 text-[10px] text-muted">
                  {EXTRACTION_STATUS_LABELS[document.extraction_status] ??
                    document.extraction_status}
                </span>
              </li>
            ))}
          </ul>
        )}
        {canWrite && <DocumentUpload entityId={entity.id} />}
      </section>

      {pendingProposals.length > 0 && (
        <section className="rounded-card border border-border bg-surface p-5">
          <h2 className="mb-1 text-sm font-semibold tracking-wide text-muted uppercase">
            Onay bekleyen öneriler
          </h2>
          <p className="mb-3 text-xs text-muted">
            Belgeden çıkarılan bilgiler onaylanmadan kütüğe işlenmez.
          </p>
          <ul className="space-y-3">
            {pendingProposals.map((proposal) => (
              <ProposalReview key={proposal.id} proposal={proposal} />
            ))}
          </ul>
        </section>
      )}

      {(openDiscrepancies.length > 0 || closedDiscrepancies.length > 0) && (
        <section className="rounded-card border border-border bg-surface p-5">
          <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted uppercase">
            Tutarsızlıklar
          </h2>
          <ul className="space-y-3">
            {[...openDiscrepancies, ...closedDiscrepancies].map((discrepancy) => (
              <DiscrepancyReview
                key={discrepancy.id}
                discrepancy={discrepancy}
                canDecide={canDecideDiscrepancy}
              />
            ))}
          </ul>
        </section>
      )}

      {/* Provenans: her değerin kim tarafından, ne zaman, nereden geldiği. */}
      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="mb-1 text-sm font-semibold tracking-wide text-muted uppercase">
          Veri kaynakları
        </h2>
        <p className="mb-3 text-xs text-muted">
          Her değerin kaynağı ve gözlem zamanı — rapordaki kanıt zinciri buradan gelir.
        </p>
        {attributes === null || attributes.length === 0 ? (
          <p className="text-sm text-muted">Kayıt yok.</p>
        ) : (
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-muted">
                <th className="pb-2 font-medium">Alan</th>
                <th className="pb-2 font-medium">Değer</th>
                <th className="pb-2 font-medium">Kaynak</th>
                <th className="pb-2 font-medium">Zaman</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {attributes.map((attribute) => (
                <tr key={attribute.id}>
                  <td className="py-1.5 text-fg">{attributeLabel(attribute.name)}</td>
                  <td className="py-1.5 font-mono text-muted">{attribute.value}</td>
                  <td className="py-1.5 text-muted">
                    {SOURCE_LABELS[attribute.source_type] ?? attribute.source_type}
                    {attribute.source_ref !== null && (
                      <span className="block text-[10px]">{attribute.source_ref}</span>
                    )}
                  </td>
                  <td className="py-1.5 text-muted">{formatDate(attribute.observed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
