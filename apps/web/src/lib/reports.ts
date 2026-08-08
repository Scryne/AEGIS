// Raporlama modülünün paylaşılan tipleri ve etiketleri (sunucu + istemci bileşenleri).
//
// Tipler backend'in OpenAPI sözleşmesini yansıtır; E1.3/E1.4'teki gibi elle tutulur
// (üretilen @aegis/api-client devreye girdiğinde buradan oraya taşınacak).

export type RiskLevel = "unknown" | "standard" | "elevated" | "high";

export interface RiskFinding {
  code: string;
  title: string;
  rationale: string;
  /** null = bulgu risk seviyesini yükseltmez, yalnız işaret eder. */
  level: RiskLevel | null;
  needs_action: boolean;
  source_refs: string[];
}

export interface RiskSummary {
  entity_id: string;
  level: RiskLevel;
  level_label: string;
  rationale: string;
  /** Karar bekleyen bulgu yoksa true — dosyanın tamamlanıp tamamlanmadığı. */
  complete: boolean;
  findings: RiskFinding[];
}

export interface Report {
  id: string;
  entity_id: string | null;
  report_type: string;
  report_format: "pdf" | "docx";
  title: string;
  risk_level: RiskLevel;
  risk_level_label: string;
  risk_rationale: string;
  risk_findings: Record<string, unknown>[];
  screening_ids: string[];
  dataset_versions: Record<string, unknown>;
  content_type: string;
  size_bytes: number;
  sha256: string;
  retention_until: string | null;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  seq: number;
  action: string;
  object_type: string;
  object_id: string | null;
  source_ref: string | null;
  actor_user_id: string | null;
  actor_label: string | null;
  actor_role: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
  row_hash: string;
}

export interface AuditEventPage {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface ChainVerification {
  ok: boolean;
  events_checked: number;
  broken_seq: number | null;
  reason: string | null;
}

/** Risk seviyesinin kenarlık/metin sınıfı — renkler tasarım belirteçlerinden (R7). */
export const RISK_CLASSES: Record<RiskLevel, string> = {
  high: "border-danger text-danger",
  elevated: "border-warning text-warning",
  unknown: "border-border text-muted",
  standard: "border-success text-success",
};

export const FORMAT_LABELS: Record<string, string> = {
  pdf: "PDF",
  docx: "Word",
};

/** Denetim izindeki eylem kodlarının Türkçe karşılıkları. */
export const ACTION_LABELS: Record<string, string> = {
  "tenant_setting.update": "Ayar değiştirildi",
  "screening.run": "Tarama çalıştırıldı",
  "match.confirm": "Eşleşme onaylandı",
  "match.dismiss": "Eşleşme elendi",
  "entity.edit": "Varlık düzenlendi",
  "entity.merge": "Varlık birleştirildi",
  "relationship.edit": "Bağ düzenlendi",
  "document.upload": "Belge yüklendi",
  "proposal.accept": "Öneri kabul edildi",
  "proposal.reject": "Öneri reddedildi",
  "discrepancy.decision": "Tutarsızlık karara bağlandı",
  "enrichment.lookup": "Dış kütük sorgulandı",
  "report.export": "Rapor dışa aktarıldı",
};

export const OBJECT_TYPE_LABELS: Record<string, string> = {
  tenant_setting: "Ayar",
  screening: "Tarama",
  match_candidate: "Eşleşme",
  entity: "Varlık",
  relationship: "Bağ",
  document: "Belge",
  extraction_proposal: "Öneri",
  discrepancy: "Tutarsızlık",
  report: "Rapor",
};

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

export function objectTypeLabel(objectType: string): string {
  return OBJECT_TYPE_LABELS[objectType] ?? objectType;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
