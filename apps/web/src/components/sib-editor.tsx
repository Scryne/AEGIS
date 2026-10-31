"use client";

// ŞİB taslağı düzenleyicisi (E2.2). Bölümler MASAK SM/SMMM/YMM rehberinin form sırasıdır (A–G).
//
// Kaydetmek hatalı taslağı da saklar (yarım iş kaybolmaz); sunucu her kayıtta rehber
// kurallarını yeniden koşar ve hataları alan alan döndürür. Word'e aktarma yalnız kaydedilmiş
// ve hatasız taslakta açılır: ekrandaki ile belgedeki aynı olmalı.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { createContext, useContext, useMemo, useState } from "react";

import {
  GIZLILIK_NOTU,
  SIB_STATUS_LABELS,
  SIB_STATUS_TONE,
  SORUMLULUK_NOTU,
  type Bulgu,
  type GercekKisi,
  type SibDetay,
  type SibForm,
  type SibKodlar,
  type SupheliIslem,
  type TuzelKisi,
} from "@/lib/sib";

type Yol = (string | number)[];

const BOS_GERCEK: GercekKisi = {
  baglanti: null,
  baglanti_aciklamasi: "",
  kimlik_sahte: false,
  ad: "",
  soyad: "",
  kimlik_belgeleri: [],
  tckn: "",
  vkn: "",
  yabanci_kimlik_veya_pasaport: "",
  uyruk: "",
  anne_adi: "",
  baba_adi: "",
  adres: "",
  dogum_tarihi: null,
  dogum_yeri: "",
  telefon: "",
  eposta: "",
  is_meslek: "",
  ek_bilgi: "",
  kaynak_varlik_id: null,
};
const BOS_TUZEL: TuzelKisi = {
  baglanti: null,
  baglanti_aciklamasi: "",
  belge_sahte: false,
  kurulus_nevi: null,
  unvan: "",
  isletme_adi: "",
  vkn: "",
  sicil_no: "",
  kurulus_ulkesi: "",
  kurulus_yeri: "",
  kurulus_tarihi: null,
  adres: "",
  faaliyet_konusu: "",
  telefon: "",
  eposta: "",
  web_sitesi: "",
  ek_bilgi: "",
  kaynak_varlik_id: null,
};
const BOS_ISLEM: SupheliIslem = {
  durum: null,
  cesit: null,
  tarih: null,
  bitis_tarihi: null,
  para_birimi: "TRY",
  tutar: null,
  tutar_tl: null,
  ulke: "Türkiye",
  il: "",
  ilce: "",
  aciklama: "",
};

/** ["gercek_kisiler", 0, "ad"] → "gercek_kisiler[0].ad" (sunucunun alan yazımı). */
function anahtar(yol: Yol): string {
  return yol.reduce<string>(
    (acc, p) => (typeof p === "number" ? `${acc}[${p}]` : acc ? `${acc}.${p}` : p),
    "",
  );
}

function yaz<T>(kok: T, yol: Yol, deger: unknown): T {
  const kopya = structuredClone(kok) as Record<string | number, unknown>;
  let hedef = kopya;
  for (const p of yol.slice(0, -1)) hedef = hedef[p] as Record<string | number, unknown>;
  hedef[yol[yol.length - 1]!] = deger;
  return kopya as T;
}

const giris =
  "w-full min-w-0 rounded-md border bg-surface px-3 py-1.5 text-sm text-fg aria-[invalid=true]:border-danger";


interface FormBaglamiDegeri {
  form: SibForm;
  set: (yol: Yol, deger: unknown) => void;
  hataHaritasi: Map<string, string>;
  kilitli: boolean;
}

// Alan bileşeni editörün DIŞINDA tanımlı ve durumu bağlamdan okur: içeride tanımlansaydı her
// tuş vuruşunda yeni bir bileşen türü oluşur, girdi yeniden bağlanır ve odak kaybolurdu.
const FormBaglami = createContext<FormBaglamiDegeri>({
  form: {} as SibForm,
  set: () => undefined,
  hataHaritasi: new Map(),
  kilitli: false,
});

function Alan({
  yol,
  etiket,
  tur = "metin",
  secenekler,
  ipucu,
  genis = false,
}: {
  yol: Yol;
  etiket: string;
  tur?: "metin" | "tarih" | "secim" | "onay" | "sayi";
  secenekler?: Record<string, string>;
  ipucu?: string;
  genis?: boolean;
}) {
  const { form, set, hataHaritasi, kilitli } = useContext(FormBaglami);
  const k = anahtar(yol);
  const id = `alan-${k.replace(/[^a-z0-9]/gi, "-")}`;
  const deger = yol.reduce<unknown>(
    (acc, p) => (acc as Record<string | number, unknown>)[p],
    form,
  );
  const hata = hataHaritasi.get(k);
  const ortak = {
    id,
    disabled: kilitli,
    "aria-invalid": hata ? true : undefined,
    "aria-describedby": hata ? `${id}-hata` : undefined,
  };
  return (
    <div className={genis ? "sm:col-span-2" : undefined}>
      {tur === "onay" ? (
        <label htmlFor={id} className="flex items-center gap-2 text-sm text-fg">
          <input
            type="checkbox"
            {...ortak}
            checked={Boolean(deger)}
            onChange={(e) => set(yol, e.target.checked)}
          />
          {etiket}
        </label>
      ) : (
        <>
          <label htmlFor={id} className="mb-1 block text-xs font-medium text-muted">
            {etiket}
          </label>
          {tur === "secim" ? (
            <select
              {...ortak}
              className={giris}
              value={(deger as string | null) ?? ""}
              onChange={(e) => set(yol, e.target.value === "" ? null : e.target.value)}
            >
              <option value="">Seçin…</option>
              {Object.entries(secenekler ?? {}).map(([kod, ad]) => (
                <option key={kod} value={kod}>
                  {ad}
                </option>
              ))}
            </select>
          ) : (
            <input
              {...ortak}
              className={giris}
              type={tur === "tarih" ? "date" : "text"}
              inputMode={tur === "sayi" ? "decimal" : undefined}
              value={(deger as string | null) ?? ""}
              onChange={(e) =>
                set(yol, e.target.value === "" && (tur === "tarih" || tur === "sayi") ? null : e.target.value)
              }
            />
          )}
        </>
      )}
      {ipucu && !hata && <p className="mt-1 text-xs text-muted">{ipucu}</p>}
      {hata && (
        <p id={`${id}-hata`} className="mt-1 text-xs text-danger">
          {hata}
        </p>
      )}
    </div>
  );
}

export function SibEditor({ detay, kodlar }: { detay: SibDetay; kodlar: SibKodlar }) {
  const router = useRouter();
  const [form, setForm] = useState<SibForm>(detay.form);
  const [kayitli, setKayitli] = useState<string>(JSON.stringify(detay.form));
  const [hatalar, setHatalar] = useState<Bulgu[]>(detay.hatalar);
  const [uyarilar, setUyarilar] = useState<Bulgu[]>(detay.uyarilar);
  const [durum, setDurum] = useState(detay.status);
  const [mesgul, setMesgul] = useState<string | null>(null);
  const [bildiri, setBildiri] = useState<{ tur: "hata" | "tamam"; metin: string } | null>(null);
  const [iptalNedeni, setIptalNedeni] = useState("");
  const [skAra, setSkAra] = useState("");

  const kilitli = durum === "iptal";
  const degisti = JSON.stringify(form) !== kayitli;
  const hataHaritasi = useMemo(() => {
    const m = new Map<string, string>();
    for (const h of hatalar) if (!m.has(h.alan)) m.set(h.alan, h.mesaj);
    return m;
  }, [hatalar]);

  const set = (yol: Yol, deger: unknown) => setForm((f) => yaz(f, yol, deger));

  async function kaydet(): Promise<boolean> {
    setMesgul("kaydet");
    setBildiri(null);
    try {
      const res = await fetch(`/api/v1/sib-drafts/${detay.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(form),
      });
      const body = (await res.json().catch(() => null)) as
        | (SibDetay & { error?: { message?: string } })
        | null;
      if (!res.ok || body === null || !("form" in body)) {
        setBildiri({ tur: "hata", metin: body?.error?.message ?? "Kaydedilemedi. Alanların biçimini kontrol edin." });
        return false;
      }
      setForm(body.form);
      setKayitli(JSON.stringify(body.form));
      setHatalar(body.hatalar);
      setUyarilar(body.uyarilar);
      setDurum(body.status);
      setBildiri({
        tur: "tamam",
        metin: body.hatalar.length
          ? `Kaydedildi. Dışa aktarmadan önce ${body.hatalar.length} eksik giderilmeli.`
          : "Kaydedildi. Taslak dışa aktarılmaya hazır.",
      });
      router.refresh();
      return true;
    } catch {
      setBildiri({ tur: "hata", metin: "Sunucuya ulaşılamadı." });
      return false;
    } finally {
      setMesgul(null);
    }
  }

  async function disaAktar() {
    setMesgul("aktar");
    setBildiri(null);
    try {
      const res = await fetch(`/api/v1/sib-drafts/${detay.id}/export`, { method: "POST" });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as
          | { error?: { message?: string; details?: Bulgu[] } }
          | null;
        if (body?.error?.details) setHatalar(body.error.details);
        setBildiri({ tur: "hata", metin: body?.error?.message ?? "Dışa aktarılamadı." });
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${detay.reference_no}-taslak.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setDurum("disa_aktarildi");
      setBildiri({
        tur: "tamam",
        metin: "Word belgesi indirildi ve denetim izine yazıldı. Belgeyi MASAK Online girişinden sonra güvenle imha edin.",
      });
      router.refresh();
    } catch {
      setBildiri({ tur: "hata", metin: "Sunucuya ulaşılamadı." });
    } finally {
      setMesgul(null);
    }
  }

  async function iptalEt() {
    setMesgul("iptal");
    try {
      const res = await fetch(`/api/v1/sib-drafts/${detay.id}/cancel`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ neden: iptalNedeni.trim() }),
      });
      if (!res.ok) {
        setBildiri({ tur: "hata", metin: "İptal edilemedi. Gerekçe en az 10 karakter olmalı." });
        return;
      }
      setDurum("iptal");
      router.refresh();
    } finally {
      setMesgul(null);
    }
  }

  const sk = form.sk_kodlari;
  const zorunluSk = form.bildirim.kategori ? kodlar.kategori_zorunlu_sk[form.bildirim.kategori] : undefined;
  const skListesi = Object.entries(kodlar.sk_kodlari).filter(
    ([kod, ad]) => !skAra || `${kod} ${ad}`.toLocaleLowerCase("tr").includes(skAra.toLocaleLowerCase("tr")),
  );
  const uzunluk = form.aciklama.length;
  const disaAktarilabilir = !degisti && hatalar.length === 0 && !kilitli;

  return (
    <FormBaglami.Provider value={{ form, set, hataHaritasi, kilitli }}>
    <div className="space-y-6 pb-24">
      <div>
        <Link href="/sib" className="text-xs text-muted hover:text-fg">
          ← ŞİB taslakları
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-2xl font-semibold text-fg">{detay.reference_no}</h1>
          <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${SIB_STATUS_TONE[durum]}`}>
            {SIB_STATUS_LABELS[durum]}
          </span>
        </div>
        <p className="mt-1 text-sm text-muted">
          <Link href={`/entities/${detay.entity_id}`} className="underline">
            {detay.entity_name}
          </Link>{" "}
          · Alan yapısı {detay.guide_version} ({kodlar.rehber.tarih})
        </p>
      </div>

      <div className="space-y-2 rounded-card border border-danger bg-surface p-4 text-sm">
        <p className="font-semibold text-danger">Gizli · Taslak</p>
        <p className="text-danger">{GIZLILIK_NOTU}</p>
        <p className="text-fg">{SORUMLULUK_NOTU}</p>
      </div>

      {kilitli && (
        <div className="rounded-card border border-border bg-surface p-4 text-sm text-muted">
          Bu taslak iptal edildi{detay.cancel_reason ? `: ${detay.cancel_reason}` : "."} Kayıt saklama süresi
          boyunca silinmez.
        </div>
      )}

      <section aria-labelledby="denetim" className="rounded-card border border-border bg-surface p-5">
        <h2 id="denetim" className="text-sm font-semibold text-fg">
          Rehber denetimi
        </h2>
        {hatalar.length === 0 ? (
          <p className="mt-2 text-sm text-success">Engelleyen eksik yok.</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm text-danger">
            {hatalar.map((h) => (
              <li key={`${h.alan}-${h.mesaj}`}>{h.mesaj}</li>
            ))}
          </ul>
        )}
        {uyarilar.length > 0 && (
          <ul className="mt-3 space-y-1 border-t border-border pt-3 text-sm text-warning">
            {uyarilar.map((u) => (
              <li key={`${u.alan}-${u.mesaj}`}>{u.mesaj}</li>
            ))}
          </ul>
        )}
        {degisti && (
          <p className="mt-3 text-xs text-muted">Kaydedilmemiş değişiklik var; denetim kayıtta yenilenir.</p>
        )}
      </section>

      <fieldset className="space-y-4 rounded-card border border-border bg-surface p-5" disabled={kilitli}>
        <legend className="px-1 text-sm font-semibold text-fg">(A) Formu düzenleyen yükümlü</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Alan yol={["yukumlu", "ad_unvan"]} etiket="Ad soyad veya unvan" />
          <Alan yol={["yukumlu", "kimlik_no"]} etiket="TCKN / VKN / YKN" />
          <Alan yol={["yukumlu", "temsilci_ad_soyad"]} etiket="Bildirimde bulunan temsilci" />
          <Alan yol={["yukumlu", "temsilci_kimlik_no"]} etiket="Temsilcinin TCKN / YKN" />
        </div>
      </fieldset>

      <fieldset className="space-y-4 rounded-card border border-border bg-surface p-5" disabled={kilitli}>
        <legend className="px-1 text-sm font-semibold text-fg">(B) Bildirime ilişkin bilgiler</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Alan yol={["bildirim", "tur"]} etiket="Yeni veya ek" tur="secim" secenekler={{ yeni: "Yeni", ek: "Ek" }} />
          {form.bildirim.tur === "ek" && (
            <Alan
              yol={["bildirim", "onceki_referans_no"]}
              etiket="Önceki bildirimin referans no"
              ipucu="Zincirleme değil, ilk bildirimin numarası."
            />
          )}
          <Alan yol={["bildirim", "kategori"]} etiket="Bildirim kategorisi" tur="secim" secenekler={kodlar.kategoriler} />
          {form.bildirim.kategori === "teror" && (
            <Alan
              yol={["bildirim", "teror_orgut_turu"]}
              etiket="Terör örgütü türü"
              tur="secim"
              secenekler={kodlar.teror_orgut_turleri}
            />
          )}
          <Alan
            yol={["bildirim", "aciliyet"]}
            etiket="Aciliyet"
            tur="secim"
            secenekler={kodlar.aciliyet}
            ipucu="Gereksiz ivedilik başka bir vakanın değerlendirmesini geciktirir."
          />
        </div>
      </fieldset>

      <fieldset className="space-y-4 rounded-card border border-border bg-surface p-5" disabled={kilitli}>
        <legend className="px-1 text-sm font-semibold text-fg">(C) Gerçek kişiler</legend>
        {form.gercek_kisiler.map((_, i) => (
          <div key={`g-${i}`} className="space-y-4 rounded-md border border-border p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-fg">Gerçek kişi {i + 1}</h3>
              <button
                type="button"
                className="text-xs text-danger underline"
                onClick={() => set(["gercek_kisiler"], form.gercek_kisiler.filter((__, j) => j !== i))}
              >
                Kaldır
              </button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Alan yol={["gercek_kisiler", i, "baglanti"]} etiket="İşlemle bağlantısı" tur="secim" secenekler={kodlar.gercek_baglanti} />
              {form.gercek_kisiler[i]?.baglanti === "dolayli" && (
                <Alan yol={["gercek_kisiler", i, "baglanti_aciklamasi"]} etiket="İlişkinin mahiyeti" />
              )}
              <Alan yol={["gercek_kisiler", i, "ad"]} etiket="Adı (kısaltmasız)" />
              <Alan yol={["gercek_kisiler", i, "soyad"]} etiket="Soyadı" />
              <Alan yol={["gercek_kisiler", i, "tckn"]} etiket="T.C. kimlik no" />
              <Alan yol={["gercek_kisiler", i, "vkn"]} etiket="Vergi kimlik no" />
              <Alan yol={["gercek_kisiler", i, "yabanci_kimlik_veya_pasaport"]} etiket="Yabancı kimlik / pasaport no" />
              <Alan yol={["gercek_kisiler", i, "uyruk"]} etiket="Uyruğu" />
              <Alan yol={["gercek_kisiler", i, "anne_adi"]} etiket="Anne adı" />
              <Alan yol={["gercek_kisiler", i, "baba_adi"]} etiket="Baba adı" />
              <Alan yol={["gercek_kisiler", i, "dogum_tarihi"]} etiket="Doğum tarihi" tur="tarih" />
              <Alan yol={["gercek_kisiler", i, "dogum_yeri"]} etiket="Doğum yeri" />
              <Alan yol={["gercek_kisiler", i, "adres"]} etiket="Adres (ilçe-il-posta kodu)" genis />
              <Alan yol={["gercek_kisiler", i, "telefon"]} etiket="Telefon (ülke kodlu)" />
              <Alan yol={["gercek_kisiler", i, "eposta"]} etiket="E-posta" />
              <Alan yol={["gercek_kisiler", i, "is_meslek"]} etiket="İş ve meslek" />
              <Alan yol={["gercek_kisiler", i, "ek_bilgi"]} etiket="Varsa ek bilgi" genis />
              <Alan yol={["gercek_kisiler", i, "kimlik_sahte"]} etiket="Kimlik belgesi veya beyanı sahte" tur="onay" />
            </div>
          </div>
        ))}
        <button
          type="button"
          className="rounded-md border border-border px-3 py-1.5 text-sm text-fg"
          onClick={() => set(["gercek_kisiler"], [...form.gercek_kisiler, structuredClone(BOS_GERCEK)])}
        >
          Gerçek kişi ekle
        </button>
      </fieldset>

      <fieldset className="space-y-4 rounded-card border border-border bg-surface p-5" disabled={kilitli}>
        <legend className="px-1 text-sm font-semibold text-fg">(D) Tüzel / diğer kişiler</legend>
        {form.tuzel_kisiler.map((_, i) => (
          <div key={`t-${i}`} className="space-y-4 rounded-md border border-border p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-fg">Tüzel/diğer kişi {i + 1}</h3>
              <button
                type="button"
                className="text-xs text-danger underline"
                onClick={() => set(["tuzel_kisiler"], form.tuzel_kisiler.filter((__, j) => j !== i))}
              >
                Kaldır
              </button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Alan yol={["tuzel_kisiler", i, "baglanti"]} etiket="İşlemle bağlantısı" tur="secim" secenekler={kodlar.tuzel_baglanti} />
              {form.tuzel_kisiler[i]?.baglanti === "dolayli" && (
                <Alan yol={["tuzel_kisiler", i, "baglanti_aciklamasi"]} etiket="İlişkinin mahiyeti" />
              )}
              <Alan yol={["tuzel_kisiler", i, "kurulus_nevi"]} etiket="Kuruluş nev'i" tur="secim" secenekler={kodlar.kurulus_nevi} />
              <Alan yol={["tuzel_kisiler", i, "unvan"]} etiket="Unvan (nev'i dahil)" genis />
              <Alan yol={["tuzel_kisiler", i, "isletme_adi"]} etiket="İşletme adı" />
              <Alan yol={["tuzel_kisiler", i, "vkn"]} etiket="Vergi kimlik no" />
              <Alan yol={["tuzel_kisiler", i, "sicil_no"]} etiket="Sicil / MERSİS no" />
              <Alan yol={["tuzel_kisiler", i, "kurulus_ulkesi"]} etiket="Kurulduğu ülke" />
              <Alan yol={["tuzel_kisiler", i, "kurulus_yeri"]} etiket="Kurulduğu yer (il-ilçe)" />
              <Alan yol={["tuzel_kisiler", i, "kurulus_tarihi"]} etiket="Kuruluş tarihi" tur="tarih" />
              <Alan yol={["tuzel_kisiler", i, "adres"]} etiket="Adresi (merkez)" genis />
              <Alan yol={["tuzel_kisiler", i, "faaliyet_konusu"]} etiket="Faaliyet konusu (kod + açıklama)" genis />
              <Alan yol={["tuzel_kisiler", i, "telefon"]} etiket="Telefon" />
              <Alan yol={["tuzel_kisiler", i, "eposta"]} etiket="E-posta" />
              <Alan yol={["tuzel_kisiler", i, "web_sitesi"]} etiket="Web sitesi" />
              <Alan yol={["tuzel_kisiler", i, "ek_bilgi"]} etiket="Varsa ek bilgi" genis />
              <Alan yol={["tuzel_kisiler", i, "belge_sahte"]} etiket="Kimliğe esas belge sahte" tur="onay" />
            </div>
          </div>
        ))}
        <button
          type="button"
          className="rounded-md border border-border px-3 py-1.5 text-sm text-fg"
          onClick={() => set(["tuzel_kisiler"], [...form.tuzel_kisiler, structuredClone(BOS_TUZEL)])}
        >
          Tüzel/diğer kişi ekle
        </button>
        {hataHaritasi.get("kisiler") && <p className="text-xs text-danger">{hataHaritasi.get("kisiler")}</p>}
      </fieldset>

      <fieldset className="space-y-4 rounded-card border border-border bg-surface p-5" disabled={kilitli}>
        <legend className="px-1 text-sm font-semibold text-fg">(E) Şüpheli işlemler</legend>
        <p className="text-xs text-muted">
          Yalnız parasal tutar içeren ve şüphe duyulan işlemler. Tutar yoksa (hesap açılışı, vekâlet gibi)
          bu bölümü boş bırakın, hususu açıklamada anlatın.
        </p>
        {form.islemler.map((_, i) => (
          <div key={`e-${i}`} className="space-y-4 rounded-md border border-border p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-fg">Şüpheli işlem {i + 1}</h3>
              <button
                type="button"
                className="text-xs text-danger underline"
                onClick={() => set(["islemler"], form.islemler.filter((__, j) => j !== i))}
              >
                Kaldır
              </button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Alan yol={["islemler", i, "durum"]} etiket="İşlem durumu" tur="secim" secenekler={kodlar.islem_durumu} />
              <Alan yol={["islemler", i, "cesit"]} etiket="İşlem çeşidi" tur="secim" secenekler={kodlar.islem_cesidi} />
              <Alan yol={["islemler", i, "tarih"]} etiket="İşlem tarihi (başlangıç)" tur="tarih" />
              {form.islemler[i]?.cesit === "coklu" && (
                <Alan yol={["islemler", i, "bitis_tarihi"]} etiket="Bitiş tarihi" tur="tarih" />
              )}
              <Alan yol={["islemler", i, "para_birimi"]} etiket="Para birimi" />
              <Alan yol={["islemler", i, "tutar"]} etiket="İşlem tutarı" tur="sayi" ipucu="Ondalık için nokta: 125000.50" />
              {form.islemler[i]?.para_birimi.toUpperCase() !== "TRY" && (
                <Alan yol={["islemler", i, "tutar_tl"]} etiket="Tutar (TL karşılığı)" tur="sayi" />
              )}
              <Alan yol={["islemler", i, "ulke"]} etiket="Ülke" />
              <Alan yol={["islemler", i, "il"]} etiket="İl" />
              <Alan yol={["islemler", i, "ilce"]} etiket="İlçe" />
              <Alan yol={["islemler", i, "aciklama"]} etiket="İşlem açıklaması (beyan edilen)" genis />
            </div>
          </div>
        ))}
        <button
          type="button"
          className="rounded-md border border-border px-3 py-1.5 text-sm text-fg"
          onClick={() => set(["islemler"], [...form.islemler, structuredClone(BOS_ISLEM)])}
        >
          Şüpheli işlem ekle
        </button>
      </fieldset>

      <fieldset className="space-y-3 rounded-card border border-border bg-surface p-5" disabled={kilitli}>
        <legend className="px-1 text-sm font-semibold text-fg">(F) Şüphe kategorisi</legend>
        <p className="text-xs text-muted">
          En az {kodlar.sk_en_az}, en fazla {kodlar.sk_en_cok} kod. Seçim bir suç hükmü değildir.
          {zorunluSk && ` Bu kategoride ${zorunluSk.join(" ya da ")} kullanılmalı.`}
        </p>
        {sk.length > 0 && (
          <ul className="flex flex-wrap gap-2" aria-label="Seçili kodlar">
            {sk.map((kod) => (
              <li key={kod} className="rounded-full border border-primary px-2 py-0.5 text-xs text-primary">
                {kod} {kodlar.sk_kodlari[kod]}
              </li>
            ))}
          </ul>
        )}
        <label htmlFor="sk-ara" className="sr-only">
          Şüphe kategorisi ara
        </label>
        <input
          id="sk-ara"
          value={skAra}
          onChange={(e) => setSkAra(e.target.value)}
          placeholder="Kod ya da ad ile ara…"
          className={`${giris} border-border`}
        />
        <div className="max-h-72 space-y-1 overflow-y-auto rounded-md border border-border p-2">
          {skListesi.map(([kod, ad]) => {
            const secili = sk.includes(kod);
            return (
              <label key={kod} className="flex items-start gap-2 rounded px-1 py-1 text-sm text-fg hover:bg-bg">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={secili}
                  disabled={!secili && sk.length >= kodlar.sk_en_cok}
                  onChange={(e) =>
                    set(["sk_kodlari"], e.target.checked ? [...sk, kod] : sk.filter((x) => x !== kod))
                  }
                />
                <span>
                  <span className="font-mono text-xs text-muted">{kod}</span> {ad}
                </span>
              </label>
            );
          })}
        </div>
        {hataHaritasi.get("sk_kodlari") && <p className="text-xs text-danger">{hataHaritasi.get("sk_kodlari")}</p>}
      </fieldset>

      <fieldset className="space-y-2 rounded-card border border-border bg-surface p-5" disabled={kilitli}>
        <legend className="px-1 text-sm font-semibold text-fg">(G) Açıklama</legend>
        <p className="text-xs text-muted">
          Şüphe duyulan eylem, yapılan tüm araştırma ve sonuçları, fonların kaynağı. Açıklamada adı geçen
          her kişi C/D bölümlerinde de yer almalı. Otomatik iskelet olduğu gibi gönderilemez.
        </p>
        <label htmlFor="aciklama" className="sr-only">
          Açıklama
        </label>
        <textarea
          id="aciklama"
          rows={16}
          value={form.aciklama}
          onChange={(e) => set(["aciklama"], e.target.value)}
          aria-invalid={hataHaritasi.has("aciklama") || undefined}
          aria-describedby="aciklama-sayac"
          className={`${giris} font-[inherit] leading-relaxed`}
        />
        <p id="aciklama-sayac" className={`text-xs ${uzunluk < kodlar.aciklama_en_az ? "text-danger" : "text-muted"}`}>
          {uzunluk.toLocaleString("tr-TR")} / {kodlar.aciklama_en_cok.toLocaleString("tr-TR")} karakter · en az{" "}
          {kodlar.aciklama_en_az}
        </p>
        {hataHaritasi.get("aciklama") && <p className="text-xs text-danger">{hataHaritasi.get("aciklama")}</p>}
      </fieldset>

      {!kilitli && (
        <details className="rounded-card border border-border bg-surface p-5">
          <summary className="cursor-pointer text-sm font-medium text-fg">Taslağı iptal et</summary>
          <div className="mt-3 space-y-2">
            <label htmlFor="iptal-neden" className="block text-xs font-medium text-muted">
              Gerekçe (en az 10 karakter; taslak silinmez)
            </label>
            <input
              id="iptal-neden"
              value={iptalNedeni}
              onChange={(e) => setIptalNedeni(e.target.value)}
              className={`${giris} border-border`}
            />
            <button
              type="button"
              onClick={iptalEt}
              disabled={iptalNedeni.trim().length < 10 || mesgul !== null}
              className="rounded-md border border-danger px-3 py-1.5 text-sm text-danger disabled:opacity-50"
            >
              İptal et
            </button>
          </div>
        </details>
      )}

      {!kilitli && (
        <div className="sticky bottom-0 -mx-4 flex flex-col gap-2 border-t border-border bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p role="status" className={`text-sm ${bildiri?.tur === "hata" ? "text-danger" : "text-muted"}`}>
            {bildiri?.metin ??
              (degisti ? "Kaydedilmemiş değişiklik var." : hatalar.length ? `${hatalar.length} eksik var.` : "Dışa aktarılmaya hazır.")}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={kaydet}
              disabled={mesgul !== null || !degisti}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-fg disabled:opacity-50"
            >
              {mesgul === "kaydet" ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button
              type="button"
              onClick={disaAktar}
              disabled={mesgul !== null || !disaAktarilabilir}
              title={degisti ? "Önce kaydedin" : hatalar.length ? "Eksikler giderilmeli" : undefined}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-fg disabled:opacity-50"
            >
              {mesgul === "aktar" ? "Hazırlanıyor…" : "Word olarak dışa aktar"}
            </button>
          </div>
        </div>
      )}
    </div>
    </FormBaglami.Provider>
  );
}
