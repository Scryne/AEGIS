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
  high: "border-danger/40 bg-danger-soft text-danger",
  elevated: "border-warning/40 bg-warning-soft text-warning",
  unknown: "border-border text-muted",
  standard: "border-success/40 bg-success-soft text-success",
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
  "document.extraction_retry": "Çıkarım yeniden denendi",
  "proposal.accept": "Öneri kabul edildi",
  "proposal.reject": "Öneri reddedildi",
  "discrepancy.decision": "Tutarsızlık karara bağlandı",
  "enrichment.lookup": "Dış kütük sorgulandı",
  "report.export": "Rapor dışa aktarıldı",
  "ubo.compute": "Gerçek faydalanıcı hesaplandı",
  "risk_score.snapshot": "Risk puanı kayda geçirildi",
  "monitoring.toggle": "İzleme durumu değişti",
  "monitoring.alert": "İzleme alarmı üretildi",
  "monitoring.acknowledge": "İzleme alarmı görüldü",
  "sib.create": "ŞİB taslağı açıldı",
  "sib.update": "ŞİB taslağı düzenlendi",
  "sib.export": "ŞİB taslağı dışa aktarıldı",
  "sib.cancel": "ŞİB taslağı iptal edildi",
  "adverse_media.scan": "Olumsuz haber tarandı",
  "adverse_media.review": "Olumsuz haber incelendi",
  "adverse_media.beta_toggle": "Olumsuz haber betası değişti",
  "case.open": "Vaka açıldı",
  "case.transition": "Vaka durumu değişti",
  "case.assign": "Vaka atandı",
  "case.due": "Vaka süresi değişti",
  "case.edd_item": "Güçlendirilmiş inceleme adımı",
  "case.comment": "Vakaya not eklendi",
  "batch.create": "Toplu tarama yüklendi",
  "batch.start": "Toplu tarama başladı",
  "batch.row_resolve": "Toplu tarama satırı eşlendi",
  "batch.cancel": "Toplu tarama iptal edildi",
  "batch.complete": "Toplu tarama tamamlandı",
  "api_key.create": "API anahtarı açıldı",
  "api_key.revoke": "API anahtarı iptal edildi",
  "webhook.create": "Webhook eklendi",
  "webhook.update": "Webhook değişti",
  "quality.snapshot": "Kalite ölçümü kaydedildi",
  "retention.dry_run": "Saklama süresi raporu",
  "tenant.provision": "Kurum hesabı açıldı",
  "tenant.invite": "Sahibe davet gönderildi",
  "member.invite": "Ekibe üye davet edildi",
  "member.role_change": "Üyenin rolü değişti",
  "member.remove": "Üye kurumdan çıkarıldı",
  "data.unreadable": "Şifreli kayıt çözülemedi",
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
  organization: "Kurum",
  api_key: "API anahtarı",
  match_eval_run: "Kalite ölçümü",
  monitoring_alert: "İzleme alarmı",
  retention: "Saklama",
  risk_score_snapshot: "Risk puanı",
  sib_draft: "ŞİB taslağı",
  ubo_computation: "Gerçek faydalanıcı hesabı",
  user_account: "Kullanıcı",
  webhook_endpoint: "Webhook",
  screening_batch: "Toplu tarama",
  compliance_case: "Vaka",
  adverse_media: "Olumsuz haber",
};

/** Denetim olayını yazan aktörün rolü (insan rolleri + sistem süreçleri). */
export const ACTOR_ROLE_LABELS: Record<string, string> = {
  owner: "Sahip",
  compliance_officer: "Uyum uzmanı",
  analyst: "Analist",
  auditor: "Denetçi",
  monitoring: "Gece izlemesi",
  worker: "Arka plan işi",
  system: "Sistem",
  api_key: "API anahtarı",
  operator: "AEGIS operatörü",
};

export function actorRoleLabel(role: string): string {
  return ACTOR_ROLE_LABELS[role] ?? role;
}

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
