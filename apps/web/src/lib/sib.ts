// ŞİB taslağı tipleri (E2.2) — backend `aegis_api.routers.v1.sib` ile birebir.

export type SibStatus = "taslak" | "disa_aktarildi" | "iptal";

export interface KimlikBelgesi {
  tur: string;
  numara: string;
  gecerlilik: string | null;
}

export interface GercekKisi {
  baglanti: string | null;
  baglanti_aciklamasi: string;
  kimlik_sahte: boolean;
  ad: string;
  soyad: string;
  kimlik_belgeleri: KimlikBelgesi[];
  tckn: string;
  vkn: string;
  yabanci_kimlik_veya_pasaport: string;
  uyruk: string;
  anne_adi: string;
  baba_adi: string;
  adres: string;
  dogum_tarihi: string | null;
  dogum_yeri: string;
  telefon: string;
  eposta: string;
  is_meslek: string;
  ek_bilgi: string;
  kaynak_varlik_id: string | null;
}

export interface TuzelKisi {
  baglanti: string | null;
  baglanti_aciklamasi: string;
  belge_sahte: boolean;
  kurulus_nevi: string | null;
  unvan: string;
  isletme_adi: string;
  vkn: string;
  sicil_no: string;
  kurulus_ulkesi: string;
  kurulus_yeri: string;
  kurulus_tarihi: string | null;
  adres: string;
  faaliyet_konusu: string;
  telefon: string;
  eposta: string;
  web_sitesi: string;
  ek_bilgi: string;
  kaynak_varlik_id: string | null;
}

export interface SupheliIslem {
  durum: string | null;
  cesit: string | null;
  tarih: string | null;
  bitis_tarihi: string | null;
  para_birimi: string;
  tutar: string | null;
  tutar_tl: string | null;
  ulke: string;
  il: string;
  ilce: string;
  aciklama: string;
}

export interface SibForm {
  yukumlu: { ad_unvan: string; kimlik_no: string; temsilci_ad_soyad: string; temsilci_kimlik_no: string };
  bildirim: {
    tur: "yeni" | "ek";
    onceki_referans_no: string;
    kategori: string | null;
    teror_orgut_turu: string | null;
    aciliyet: string;
  };
  gercek_kisiler: GercekKisi[];
  tuzel_kisiler: TuzelKisi[];
  islemler: SupheliIslem[];
  sk_kodlari: string[];
  aciklama: string;
}

export interface Bulgu {
  alan: string;
  mesaj: string;
}

export interface SibOzet {
  id: string;
  entity_id: string;
  entity_name: string;
  reference_no: string;
  status: SibStatus;
  category: string | null;
  errors: number;
  warnings: number;
  export_count: number;
  last_exported_at: string | null;
  updated_at: string;
  created_at: string;
}

export interface SibDetay extends SibOzet {
  form: SibForm;
  hatalar: Bulgu[];
  uyarilar: Bulgu[];
  guide_version: string;
  cancel_reason: string | null;
}

export interface SibKodlar {
  rehber: Record<string, string>;
  aciklama_en_az: number;
  aciklama_en_cok: number;
  sk_en_az: number;
  sk_en_cok: number;
  kategoriler: Record<string, string>;
  teror_orgut_turleri: Record<string, string>;
  aciliyet: Record<string, string>;
  gercek_baglanti: Record<string, string>;
  tuzel_baglanti: Record<string, string>;
  kurulus_nevi: Record<string, string>;
  kimlik_belgeleri: Record<string, string>;
  islem_durumu: Record<string, string>;
  islem_cesidi: Record<string, string>;
  sk_kodlari: Record<string, string>;
  kategori_zorunlu_sk: Record<string, string[]>;
}

export const SIB_STATUS_LABELS: Record<SibStatus, string> = {
  taslak: "Taslak",
  disa_aktarildi: "Dışa aktarıldı",
  iptal: "İptal",
};

export const SIB_STATUS_TONE: Record<SibStatus, string> = {
  taslak: "border-warning text-warning",
  disa_aktarildi: "border-success text-success",
  iptal: "border-border text-muted",
};

/** Yalnız sahip ve uyum görevlisi: bildirimin varlığı bile gizlidir (5549 s.K. m.4/2). */
export const SIB_ROLES = ["owner", "compliance_officer"] as const;

export const GIZLILIK_NOTU =
  "Şüpheli işlem bildiriminde bulunulduğu, işleme taraf olanlar dahil hiç kimseye açıklanamaz " +
  "(5549 sayılı Kanun m.4/2). Bu sayfa yalnız sahip ve uyum görevlisi rolüne açıktır.";

export const SORUMLULUK_NOTU =
  "AEGIS bir taslak hazırlar. Resmî bildirim, yükümlünün MASAK Online üzerinden yaptığı " +
  "bildirimdir ve sorumluluğu yükümlüye aittir.";
