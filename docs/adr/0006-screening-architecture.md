# ADR-0006: Tarama servisi mimarisi — anlık görüntü, eşik bandı ve recall kapısı

- **Durum:** Kabul edildi
- **Tarih:** 2026-08-08
- **Karar veren:** Scryne
- **İlgili:** CLAUDE.md Invariant 1 (RLS), 2 (denetim izi), 3 (veri yerelliği),
  4 (provenans/saklama); ROADMAP §7 E1.3; ADR-0002 (RLS), ADR-0003 (yente 5.5.0 pini)

## Bağlam

E1.3 taramayı getirir ama varlık kütüğü (`Entity`) E1.4'te gelir. Ayrıca tarama, ürünün
**risk-etkileyen** ana eylemidir: sonucu bir MASAK denetiminde savunulmak zorundadır.
Bu iki gerçek, birkaç kararı erken kilitlemeyi gerektirir.

## Kararlar

### 1. Tarama, varlık kütüğüne değil **özne anlık görüntüsüne** yazılır

`screening` satırı taranan öznelerin (`subjects` JSONB) o anki hâlini taşır; `entity_id`
kolonu E1.4'e boş bırakılır. İki nedenle:

- **Sıralama:** E1.3, E1.4'ten önce gelir (ROADMAP bağımlılık haritası); tarama kütüğü
  beklemeden çalışabilmelidir.
- **Denetim:** Varlığın adı sonradan düzeltilse bile eski tarama, **taradığı hâli**
  göstermeye devam etmelidir. "O gün neyi taradık" sorusunun cevabı kayıtta durmalıdır.

Aynı gerekçeyle eşikler ve veri kümesi sürümleri de koşu anında satıra dondurulur:
sonradan eşik değişirse eski karar yeniden yorumlanmaz.

### 2. Üç bölgeli eşik bandı — ama **otomatik onay yok**

`auto_dismiss_below` altındaki aday otomatik elenir (kaydı silinmez, gerekçesiyle durur);
`auto_flag_at` üstündeki aday **yine `pending` kalır**, yalnız `flagged` olur.

Yüksek skorlu bir eşleşmeyi otomatik onaylamak, ürünü "karar desteği"nden "karar veren"e
çevirirdi — Ürün Planı §8.3'teki sorumluluk duruşuyla ve pilot sözleşmesindeki
sorumluluk kaydıyla çelişir. Onay bir insan kararıdır.

Eleme kararı **gerekçe zorunludur**: MASAK denetiminde "neden elendi" cevapsız kalamaz.

### 3. Motor hatası sessizce "temiz" olmaz

yente erişilemezse koşu `failed` durumuyla kalıcılaşır, denetim olayı yazılır ve API
**502** döner (kaynak yine okunabilir). Arayüz bunu "Tarama yapılamadı — sonuç YOK
(temiz değil)" diye gösterir.

Bu ürünün en pahalı yanlış anlaşılması, "aday bulunamadı" ile "bakamadık"ın aynı ekrana
düşmesi olurdu. Aynı gerekçeyle veri **bayatlığı** (>24 sa) da tarama ekranında uyarı
üretir ve `sanctions.sync` job'ı Sentry'ye alarm gönderir.

### 4. `sanctions_dataset` tablosu RLS-muaftır (bilinçli)

Kiracıya-özel *veri* tabloları (`screening`, `match_candidate`) ENABLE+FORCE RLS alır ve
izolasyon kapısına eklenmiştir. `sanctions_dataset` ise müşteri verisi değil, kamuya açık
veri kümelerinin katalog **meta**'sıdır (ad, sürüm, son dışa aktarım): tüm kiracılar aynı
motoru paylaşır, kiracı başına kopyalamak yanlış olurdu. Kimlik/kontrol-düzlemi
tablolarıyla aynı istisna gerekçesi (ADR-0002).

### 5. Kimlik numaraları maskeli saklanır (E1.4'e kadar)

TCKN/vergi no yente sorgusunda bellekte kullanılır, `screening.subjects` JSONB'sine
**maskeli** (son 4 hane) yazılır. Bu JSONB alan-düzeyi şifreleme taşımaz; şifreli
saklama, `EncryptedString` kolonlarıyla E1.4'te `entity` tablosunda olur (ADR-0005).
Derin (kuyruğa alınan) koşuda gerçek numara göreve **mesajla** geçirilir, veritabanına
yine maskeli yazılır.

### 6. Recall kapısı iki katmanlıdır ve veri kümesi **küçüktür**

- Katman 1 (`evals/test_normalization_recall.py`): Docker'sız, her push'ta, %100 taban.
- Katman 2 (`evals/test_screening_recall.py`): gerçek yente + ES, `-m screening`.

Katman 2, OpenSanctions'ın tamamını indirmek yerine yalnız 34 referans varlıktan oluşan
kendi FtM veri kümemizi indeksler. Böylece kapı hızlı **ve kararlı** olur: upstream veri
değişimi kapıyı kırmızıya düşürmez, ölçülen şey yalnız bizim normalizasyon + sorgu
zincirimizdir. Varyantlar indekse eklenmez — eklenseydi test kendini doğrulardı.

### 7. Ekler ASCII üzerinden eşleşir

Tüzel-kişilik eki tabloları Türkçe imlayla yazılır ama eşleştirme ASCII'ye indirgenerek
yapılır. `Ltd. Şti.` ve `LTD STI` tek girdiyle yakalanır; her ekin iki imlasını ayrı
listelemek, birini unutunca sessiz bir yanlış negatif doğururdu.

## Sonuçlar

**Olumlu:** Tarama E1.4'ü beklemez; koşular kendi kendini açıklayan kanıt kayıtlarıdır;
motor arızası ve bayat veri kullanıcıya görünür; recall regresyonu CI'da yakalanır.

**Ödünler:**
- `subjects` JSONB'si normalize edilmemiş veridir; E1.4'te `entity_id` bağlandığında iki
  kaynak bir arada yaşayacak (kasıtlı: tarih dondurulmuş, bugün canlı).
- Katman 2 kapısı gerçek liste verisiyle *doğruluk* ölçmez, yalnız zincirin bütünlüğünü
  ölçer. Gerçek liste üzerindeki doğruluk pilot verisiyle E1.6'da ölçülecektir.
- MASAK kaynak dosyasının sütun düzeni doğrulanmayı bekler (`COLUMN_ALIASES`); dönüşüm
  hattının tamamı hazır, yalnız üst kaynağın biçimi teyide muhtaç.

## Alternatifler

- **Taramayı E1.4 sonrasına ertelemek:** ROADMAP kritik yolunu uzatırdı; ayrıca tarama,
  satılabilir ilk artışın gösterilebilir parçasıdır.
- **Yüksek skorda otomatik onay:** Reddedildi (karar 2'deki sorumluluk gerekçesi).
- **Elenen adayları silmek:** Reddedildi; dosya raporu (E1.5) "gerekçesiyle elenen
  eşleşmeler"i göstermek zorundadır.
- **Katman 2'de tam OpenSanctions:** Reddedildi; CI'da GB'larca indirme ve upstream'e
  bağlı kararsız kapı.

## İlgili

`packages/core/src/aegis_core/screening/` (normalization · yente · thresholds · masak ·
service); `migrations/versions/0003_screening.py`; `evals/README.md`;
`infra/yente/manifest.yml`.
