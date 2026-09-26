// Tarama modülünün paylaşılan tipleri ve etiketleri (sunucu + istemci bileşenleri).
//
// Tipler backend'in OpenAPI sözleşmesini yansıtır. E1.3'te elle tutulur; üretilen
// istemci (@aegis/api-client) devreye girdiğinde buradan oraya taşınacaktır.

export type ScreeningStatus = "queued" | "running" | "completed" | "failed";
export type MatchDecision = "pending" | "confirmed" | "dismissed";
export type MatchBand = "auto_dismiss" | "review" | "auto_flag";

export interface MatchCandidate {
  id: string;
  subject_key: string;
  subject_name: string;
  subject_role: string;
  external_id: string;
  caption: string;
  schema_type: string;
  score: number;
  band: MatchBand;
  decision: MatchDecision;
  decided_automatically: boolean;
  flagged: boolean;
  datasets: string[];
  topics: string[];
  countries: string[];
  features: Record<string, number>;
  properties: Record<string, string[]>;
  source_url: string | null;
  review_note: string | null;
  reviewed_at: string | null;
}

export interface ScreeningSummary {
  total: number;
  pending: number;
  confirmed: number;
  dismissed: number;
  flagged: number;
  flagged_pending: number;
  sanction_hits: number;
  pep_hits: number;
}

export interface SubjectSnapshot {
  key: string;
  name: string;
  normalized: string;
  ascii: string;
  stripped: string[];
  type: string;
  role: string;
  country: string | null;
  identifiers: Record<string, string>;
}

export interface Screening {
  id: string;
  status: ScreeningStatus;
  subject_name: string;
  subject_normalized: string;
  subject_type: string;
  subject_country: string | null;
  subjects: SubjectSnapshot[];
  dataset: string;
  dataset_versions: Record<string, { version: string | null; last_export_at: string | null }>;
  algorithm: string;
  thresholds: Record<string, number>;
  candidate_count: number;
  duration_ms: number | null;
  error: string | null;
  entity_id: string | null;
  created_at: string;
  completed_at: string | null;
  summary: ScreeningSummary;
}

export interface ScreeningDetail extends Screening {
  candidates: MatchCandidate[];
}

export interface ScreeningList {
  total: number;
  items: Screening[];
}

export interface DatasetState {
  name: string;
  title: string | null;
  version: string | null;
  last_export_at: string | null;
  entity_count: number | null;
  checked_at: string;
  age_hours: number | null;
  stale: boolean;
}

export interface DatasetFreshness {
  staleness_threshold_hours: number;
  any_stale: boolean;
  datasets: DatasetState[];
}

export const STATUS_LABELS: Record<ScreeningStatus, string> = {
  queued: "Kuyrukta",
  running: "Çalışıyor",
  completed: "Tamamlandı",
  failed: "Başarısız",
};

export const DECISION_LABELS: Record<MatchDecision, string> = {
  pending: "İnceleme bekliyor",
  confirmed: "Onaylandı",
  dismissed: "Elendi",
};

export const BAND_LABELS: Record<MatchBand, string> = {
  auto_dismiss: "Eşik altı",
  review: "İnceleme bandı",
  auto_flag: "Yüksek skor",
};

export const ROLE_LABELS: Record<string, string> = {
  self: "Şirketin kendisi",
  officer: "Yönetici",
  ubo: "Gerçek faydalanıcı",
  shareholder: "Ortak",
};

/** FtM konu etiketlerini okunur Türkçeye çevirir (bilinmeyen etiket olduğu gibi kalır). */
export function topicLabel(topic: string): string {
  if (topic.startsWith("sanction")) return "Yaptırım";
  if (topic.startsWith("role.pep")) return "Siyasi nüfuz (PEP)";
  if (topic.startsWith("crime")) return "Suç kaydı";
  if (topic === "debarment") return "İhaleden men";
  if (topic === "wanted") return "Arananlar";
  return topic;
}

/**
 * Bir taramanın kullanıcıya gösterilecek risk başlığı.
 *
 * `failed` durumu ASLA "temiz" sayılmaz: motor erişilemediğinde aday bulunmaması,
 * yaptırım olmadığı anlamına gelmez — bu ayrım ürünün en kritik mesajıdır.
 */
export function riskHeadline(screening: Screening): {
  tone: "danger" | "warning" | "success" | "neutral";
  text: string;
} {
  if (screening.status === "failed") {
    return { tone: "danger", text: "Tarama yapılamadı — sonuç YOK (temiz değil)" };
  }
  if (screening.status === "queued" || screening.status === "running") {
    return { tone: "neutral", text: "Tarama sürüyor" };
  }
  if (screening.summary.confirmed > 0) {
    return { tone: "danger", text: "Onaylanmış eşleşme var" };
  }
  // Elenmiş/onaylanmış yüksek skorlu aday artık "acil" değildir: yalnız bekleyenler.
  if (screening.summary.flagged_pending > 0) {
    return { tone: "danger", text: "Yüksek skorlu eşleşme — acil inceleme" };
  }
  if (screening.summary.pending > 0) {
    return { tone: "warning", text: `${screening.summary.pending} eşleşme inceleme bekliyor` };
  }
  if (screening.summary.total > 0 && screening.summary.dismissed === screening.summary.total) {
    return { tone: "success", text: "Tüm adaylar gerekçeyle elendi" };
  }
  return { tone: "success", text: "Eşik üstü eşleşme bulunamadı" };
}

export const TONE_CLASSES: Record<string, string> = {
  danger: "border-danger text-danger",
  warning: "border-warning text-warning",
  success: "border-success text-success",
  neutral: "border-border text-muted",
};

/** Eşik adlarının denetçi okuyabilir karşılığı (bkz. aegis_core.screening.thresholds). */
const THRESHOLD_LABELS: Record<string, string> = {
  candidate_cutoff: "aday eşiği",
  auto_dismiss_below: "otomatik eleme altı",
  auto_flag_at: "acil işaret",
};

/** Koşu eşiklerini "aday eşiği 0,50 · otomatik eleme altı 0,65 · acil işaret 0,85" biçiminde yazar. */
export function formatThresholds(thresholds: Record<string, number>): string {
  const order = ["candidate_cutoff", "auto_dismiss_below", "auto_flag_at"];
  const keys = [
    ...order.filter((key) => key in thresholds),
    ...Object.keys(thresholds).filter((key) => !order.includes(key)),
  ];
  return keys
    .map(
      (key) =>
        `${THRESHOLD_LABELS[key] ?? key} ${thresholds[key].toLocaleString("tr-TR", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}`,
    )
    .join(" · ");
}
