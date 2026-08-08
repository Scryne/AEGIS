// Varlık kütüğü modülünün paylaşılan tipleri ve etiketleri (E1.4).
//
// Backend'in OpenAPI sözleşmesini yansıtır; üretilen istemci (@aegis/api-client)
// devreye girdiğinde buradan oraya taşınacaktır.

export type EntitySchemaType = "Person" | "Company";
export type SourceType = "declared" | "document" | "registry" | "gleif" | "screening";

export interface IdentifierWarning {
  field: string;
  value: string;
  message: string;
}

export interface Entity {
  id: string;
  schema_type: string;
  name: string;
  name_normalized: string;
  tax_number: string | null;
  mersis_number: string | null;
  lei_code: string | null;
  trade_registry_number: string | null;
  national_id_masked: string | null;
  country: string | null;
  address: string | null;
  incorporation_date: string | null;
  birth_date: string | null;
  notes: string | null;
  status: string;
  merged_into_id: string | null;
  created_at: string;
}

export interface EntityList {
  total: number;
  items: Entity[];
}

export interface EntityAttribute {
  id: string;
  name: string;
  value: string;
  source_type: string;
  source_ref: string | null;
  document_id: string | null;
  observed_at: string;
  is_current: boolean;
}

export interface Relationship {
  id: string;
  source_entity_id: string;
  source_entity_name: string | null;
  target_entity_id: string;
  target_entity_name: string | null;
  rel_type: string;
  role_title: string | null;
  ownership_percent: number | null;
  start_date: string | null;
  end_date: string | null;
  source_type: string;
  source_ref: string | null;
  document_id: string | null;
}

export interface Discrepancy {
  id: string;
  entity_id: string;
  attribute_name: string;
  declared_value: string;
  declared_source_ref: string | null;
  observed_value: string;
  observed_source_type: string;
  observed_source_ref: string | null;
  document_id: string | null;
  severity: string;
  status: string;
  resolution_note: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface AegisDocument {
  id: string;
  entity_id: string | null;
  doc_type: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  source_ref: string | null;
  extraction_status: string;
  extraction_error: string | null;
  extraction_engine: string | null;
  page_count: number | null;
  extracted_at: string | null;
  created_at: string;
}

export interface ExtractionProposal {
  id: string;
  document_id: string;
  entity_id: string | null;
  kind: string;
  payload: Record<string, unknown>;
  confidence: number;
  evidence_text: string | null;
  page_number: number | null;
  status: string;
  review_note: string | null;
  reviewed_at: string | null;
  resulting_entity_id: string | null;
}

export interface ResolutionCandidate {
  entity_id: string;
  name: string;
  schema_type: string;
  similarity: number;
  reason: string;
  conflicting_identifier: string | null;
}

export interface ResolutionResult {
  outcome: "matched" | "ambiguous" | "new";
  matched_entity_id: string | null;
  candidates: ResolutionCandidate[];
}

export const SOURCE_LABELS: Record<string, string> = {
  declared: "Beyan",
  document: "Belge",
  registry: "Kütük",
  gleif: "GLEIF",
  screening: "Tarama",
};

export const REL_TYPE_LABELS: Record<string, string> = {
  officer: "Yönetici",
  shareholder: "Ortak",
  ubo: "Gerçek faydalanıcı",
  family: "Aile bağı",
  control: "Kontrol",
  representative: "Temsilci",
};

export const DOC_TYPE_LABELS: Record<string, string> = {
  imza_sirkuleri: "İmza sirküleri",
  faaliyet_belgesi: "Faaliyet belgesi",
  ticaret_sicil_gazetesi: "Ticaret Sicil Gazetesi",
  other: "Diğer",
};

export const EXTRACTION_STATUS_LABELS: Record<string, string> = {
  pending: "Sırada",
  running: "İşleniyor",
  completed: "Tamamlandı",
  failed: "Başarısız",
  skipped: "Çıkarım yapılmadı",
};

export const ATTRIBUTE_LABELS: Record<string, string> = {
  name: "Unvan / ad",
  address: "Adres",
  country: "Ülke",
  taxNumber: "Vergi no",
  mersisNumber: "MERSİS no",
  leiCode: "LEI",
  tradeRegistryNumber: "Ticaret sicil no",
  nationalId: "T.C. kimlik no",
  incorporationDate: "Kuruluş tarihi",
  birthDate: "Doğum tarihi",
};

export const SEVERITY_LABELS: Record<string, string> = {
  info: "Bilgi",
  warning: "Uyarı",
  critical: "Kritik",
};

export const SEVERITY_CLASSES: Record<string, string> = {
  info: "border-border text-muted",
  warning: "border-warning text-warning",
  critical: "border-danger text-danger",
};

export function attributeLabel(name: string): string {
  return ATTRIBUTE_LABELS[name] ?? name;
}
