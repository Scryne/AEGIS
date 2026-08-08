"use client";

// Çıkarım önerisi incelemesi — kabul et / reddet.
//
// Revizyon R2: belgeden çıkan hiçbir şey onaysız kütüğe girmez. Kullanıcı kanıt metnini
// görerek karar verir. Kişi önerisinde kütükte birden çok benzer kayıt varsa backend 409
// döner ve adayları listeler; kullanıcı hangisine bağlanacağını seçer.

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { ExtractionProposal } from "@/lib/entities";
import { attributeLabel } from "@/lib/entities";

interface Candidate {
  entity_id: string;
  name: string;
  similarity: number;
  reason: string;
}

function describe(proposal: ExtractionProposal): string {
  if (proposal.kind === "attribute") {
    const name = String(proposal.payload.name ?? "");
    return `${attributeLabel(name)}: ${String(proposal.payload.value ?? "")}`;
  }
  const person = String(proposal.payload.person_name ?? "");
  const role = proposal.payload.role_title ? ` — ${String(proposal.payload.role_title)}` : "";
  const tckn = proposal.payload.national_id
    ? ` (TCKN ${String(proposal.payload.national_id)})`
    : "";
  return `${person}${tckn}${role}`;
}

export function ProposalReview({ proposal }: { proposal: ExtractionProposal }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);

  async function decide(decision: "accepted" | "rejected", linkEntityId?: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/documents/${proposal.document_id}/proposals/${proposal.id}/decision`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            decision,
            note: note.trim() || null,
            link_entity_id: linkEntityId ?? null,
          }),
        },
      );
      if (res.status === 409) {
        const payload = (await res.json().catch(() => null)) as {
          error?: { details?: Candidate[] };
        } | null;
        setCandidates(payload?.error?.details ?? []);
        setError("Bu kişi kütükte birden çok kayda benziyor; hangisine bağlanacağını seçin.");
        return;
      }
      if (!res.ok) {
        const payload = (await res.json().catch(() => null)) as {
          error?: { message?: string };
        } | null;
        setError(payload?.error?.message ?? "Karar kaydedilemedi.");
        return;
      }
      router.refresh();
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setBusy(false);
    }
  }

  const decided = proposal.status !== "pending";

  return (
    <li className="rounded-card border border-border bg-bg p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm text-fg">{describe(proposal)}</div>
          <div className="mt-0.5 text-xs text-muted">
            {proposal.kind === "attribute" ? "Öznitelik" : "Kişi bağı"} · güven{" "}
            {proposal.confidence.toFixed(2)}
            {proposal.page_number !== null && ` · sayfa ${proposal.page_number}`}
          </div>
        </div>
        <span
          className={`shrink-0 rounded border px-2 py-0.5 text-xs ${
            proposal.status === "accepted"
              ? "border-success text-success"
              : proposal.status === "rejected"
                ? "border-border text-muted"
                : "border-warning text-warning"
          }`}
        >
          {proposal.status === "accepted"
            ? "Kabul edildi"
            : proposal.status === "rejected"
              ? "Reddedildi"
              : "Onay bekliyor"}
        </span>
      </div>

      {proposal.evidence_text !== null && (
        <pre className="mt-2 overflow-x-auto rounded bg-surface p-2 font-mono text-[11px] whitespace-pre-wrap text-muted">
          {proposal.evidence_text}
        </pre>
      )}

      {proposal.review_note !== null && (
        <p className="mt-2 text-xs text-muted">
          <span className="font-medium">Not:</span> {proposal.review_note}
        </p>
      )}

      {candidates !== null && candidates.length > 0 && (
        <ul className="mt-2 space-y-1">
          {candidates.map((candidate) => (
            <li key={candidate.entity_id} className="flex items-center justify-between gap-2">
              <span className="text-xs text-fg">
                {candidate.name} <span className="text-muted">({candidate.reason})</span>
              </span>
              <button
                type="button"
                disabled={busy}
                onClick={() => decide("accepted", candidate.entity_id)}
                className="rounded border border-border px-2 py-0.5 text-xs text-fg"
              >
                Buna bağla
              </button>
            </li>
          ))}
        </ul>
      )}

      {!decided && (
        <div className="mt-3 space-y-2 border-t border-border pt-3">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Karar notu (isteğe bağlı)"
            className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-fg"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => decide("accepted")}
              className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-fg disabled:opacity-50"
            >
              Kabul et
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => decide("rejected")}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-muted hover:text-fg disabled:opacity-50"
            >
              Reddet
            </button>
          </div>
        </div>
      )}

      {error !== null && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}
    </li>
  );
}
