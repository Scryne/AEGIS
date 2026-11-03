// Toplu tarama (E3.3) tipleri ve etiketleri.

export type BatchStatus = "draft" | "queued" | "running" | "completed" | "cancelled";
export type RowStatus =
  | "invalid"
  | "duplicate"
  | "pending"
  | "done"
  | "needs_review"
  | "failed"
  | "cancelled";

export interface Batch {
  id: string;
  file_name: string;
  status: BatchStatus;
  total_rows: number;
  counts: Record<RowStatus, number>;
  risk: { sanction_rows: number; pep_rows: number; flagged_rows: number };
  column_map: Record<string, string>;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ResolutionCandidate {
  entity_id: string;
  name: string;
  similarity: number;
  reason: string;
  conflicting_identifier: string | null;
}

export interface BatchRow {
  id: string;
  row_no: number;
  data: {
    name: string;
    schema_type: "Company" | "Person";
    tax_number: string | null;
    mersis_number: string | null;
    country: string | null;
    external_ref: string | null;
  };
  errors: string[];
  warnings: string[];
  status: RowStatus;
  duplicate_of: number | null;
  resolution: string | null;
  resolution_candidates: ResolutionCandidate[] | null;
  entity_id: string | null;
  screening_id: string | null;
  candidate_count: number | null;
  flagged_count: number | null;
  sanction_hits: number | null;
  pep_hits: number | null;
  top_score: number | null;
  attempts: number;
  error: string | null;
}

export const FIELD_LABELS: Record<string, string> = {
  name: "Ad / unvan",
  schema_type: "Tür (şirket/kişi)",
  tax_number: "Vergi no",
  mersis_number: "MERSİS no",
  country: "Ülke",
  external_ref: "Müşteri referansı",
};

export const BATCH_STATUS_LABELS: Record<BatchStatus, string> = {
  draft: "Taslak",
  queued: "Sırada",
  running: "İşleniyor",
  completed: "Tamamlandı",
  cancelled: "İptal edildi",
};

export const ROW_STATUS_LABELS: Record<RowStatus, string> = {
  invalid: "Geçersiz",
  duplicate: "Dosyada tekrar",
  pending: "Bekliyor",
  done: "Tarandı",
  needs_review: "Karar bekliyor",
  failed: "Başarısız",
  cancelled: "İptal",
};

export const ROW_STATUS_TONE: Record<RowStatus, string> = {
  invalid: "border-danger/40 bg-danger-soft text-danger",
  duplicate: "border-border text-muted",
  pending: "border-border text-muted",
  done: "border-border text-fg",
  needs_review: "border-warning/40 bg-warning-soft text-warning",
  failed: "border-danger/40 bg-danger-soft text-danger",
  cancelled: "border-border text-muted",
};

export const RESOLUTION_LABELS: Record<string, string> = {
  matched: "Mevcut varlık",
  new: "Yeni varlık",
  ambiguous: "Belirsiz",
  matched_by_user: "Mevcut varlık (karar)",
  new_by_user: "Yeni varlık (karar)",
};

/** Satırın risk özeti: renk yalnız riski taşır, metin her zaman yanında. */
export function rowRisk(row: BatchRow): { label: string; tone: string } {
  if ((row.sanction_hits ?? 0) > 0) return { label: "Yaptırım adayı", tone: "border-danger/40 bg-danger-soft text-danger" };
  if ((row.pep_hits ?? 0) > 0) return { label: "PEP adayı", tone: "border-warning/40 bg-warning-soft text-warning" };
  if ((row.flagged_count ?? 0) > 0) return { label: "Yüksek skorlu aday", tone: "border-warning/40 bg-warning-soft text-warning" };
  if (row.status === "done" && (row.candidate_count ?? 0) > 0) return { label: "Düşük skorlu aday", tone: "border-border text-muted" };
  if (row.status === "done") return { label: "Eşik üstü aday yok", tone: "border-success/40 bg-success-soft text-success" };
  return { label: "—", tone: "border-transparent text-muted" };
}
