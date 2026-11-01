// Vaka yönetimi (E3.2) tipleri ve etiketleri — sunucu ve istemci bileşenleri paylaşır.

export type CaseStatus = "new" | "in_review" | "escalated" | "approved" | "closed";
export type Severity = "critical" | "high" | "info";
export type CaseAction = "start_review" | "escalate" | "approve" | "close" | "reopen";

export interface CaseRow {
  id: string;
  entity_id: string;
  entity_name: string | null;
  title: string;
  source: "manual" | "monitoring_alert" | "screening";
  source_alert_id: string | null;
  source_screening_id: string | null;
  severity: Severity;
  severity_label: string;
  status: CaseStatus;
  status_label: string;
  edd: boolean;
  assignee_user_id: string | null;
  due_at: string | null;
  overdue: boolean;
  created_at: string;
  first_review_at: string | null;
  decided_at: string | null;
  closed_at: string | null;
  resolution: string | null;
}

export interface CaseSummary {
  new: number;
  in_review: number;
  escalated: number;
  approved: number;
  closed: number;
  open: number;
  overdue: number;
  unassigned: number;
  mine: number;
  edd_open: number;
}

export interface ChecklistItem {
  key: string;
  label: string;
  done: boolean;
  note: string | null;
  by: string | null;
  at: string | null;
}

export interface CaseComment {
  id: string;
  author_user_id: string | null;
  author_role: string | null;
  body: string;
  created_at: string;
}

export interface CaseHistoryEvent {
  seq: number;
  action: string;
  actor_user_id: string | null;
  actor_role: string | null;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface CaseDetail extends CaseRow {
  edd_template_version: string | null;
  edd_checklist: ChecklistItem[] | null;
  edd_complete: boolean;
  allowed_actions: CaseAction[];
  comments: CaseComment[];
  history: CaseHistoryEvent[];
}

export interface Member {
  user_id: string;
  email: string;
  full_name: string | null;
  role: string;
}

/** Derece rozeti: renk yalnız risk tonu taşır, metin her zaman yanında (DESIGN.md). */
export const SEVERITY_TONE: Record<Severity, string> = {
  critical: "border-danger bg-danger/10 text-danger",
  high: "border-warning bg-warning/10 text-fg",
  info: "border-border text-muted",
};

export const STATUS_TONE: Record<CaseStatus, string> = {
  new: "border-primary text-primary",
  in_review: "border-border text-fg",
  escalated: "border-danger text-danger",
  approved: "border-success text-fg",
  closed: "border-border text-muted",
};

export const SOURCE_LABELS: Record<CaseRow["source"], string> = {
  manual: "Elle açıldı",
  monitoring_alert: "İzleme alarmı",
  screening: "Tarama incelemesi",
};

export const ACTION_LABELS: Record<CaseAction, string> = {
  start_review: "İncelemeye al",
  escalate: "Sıkılaştırılmış incelemeye yükselt (EDD)",
  approve: "Onayla",
  close: "Kapat",
  reopen: "Yeniden aç",
};

/** Gerekçe isteyen eylemler (backend ile aynı küme; en az 10 karakter). */
export const REASON_ACTIONS: CaseAction[] = ["escalate", "approve", "close", "reopen"];

export const HISTORY_LABELS: Record<string, string> = {
  "case.open": "Vaka açıldı",
  "case.transition": "Durum değişti",
  "case.assign": "Atama",
  "case.due": "Son tarih değişti",
  "case.edd_item": "EDD maddesi",
  "case.comment": "Yorum",
};

const DAY = 24 * 60 * 60 * 1000;

/** "3 gün kaldı" / "2 gün geçti" / "bugün" — son tarih metni. */
export function dueText(dueAt: string | null, now: number = Date.now()): string {
  if (!dueAt) return "Son tarih yok";
  const diff = new Date(dueAt).getTime() - now;
  const days = Math.round(Math.abs(diff) / DAY);
  if (days === 0) return diff >= 0 ? "Bugün doluyor" : "Bugün doldu";
  return diff >= 0 ? `${days} gün kaldı` : `${days} gün geçti`;
}

export function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

export function memberLabel(members: Member[], userId: string | null): string {
  if (!userId) return "Atanmadı";
  const m = members.find((x) => x.user_id === userId);
  return m ? (m.full_name ?? m.email) : "Bilinmeyen kullanıcı";
}
