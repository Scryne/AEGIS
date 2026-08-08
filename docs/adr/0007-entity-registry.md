# ADR-0007: Varlık kütüğü — gözlem tabanlı provenans, öneri kuyruğu ve ER v1

- **Durum:** Kabul edildi
- **Tarih:** 2026-08-08
- **Karar veren:** Scryne
- **İlgili:** CLAUDE.md Invariant 1–4; ROADMAP §7 E1.4 ve Revizyonlar R1 (MERSİS yok),
  R2 (Docling Phase 1'e), R4 (embedding yerine pg_trgm); ADR-0002 (RLS), ADR-0005
  (alan şifreleme), ADR-0006 (tarama)

## Bağlam

E1.4 varlık kütüğünü getirir: şirket/kişi kayıtları, aralarındaki bağlar, belgeler ve
belgelerden çıkarılan veri. İki dış kısıt tasarımı belirledi:

- **R1:** MERSİS Phase 1'de yok. Doğrulama üç yoldan gelir: manuel beyan, belge çıkarımı,
  Ticaret Sicil Gazetesi (kılavuzlu manuel).
- **R2:** Docling Phase 1'e alındı ama **iki belge türüyle** ve **kullanıcı onaylı
  önerilerle** sınırlı.

Ayrıca E1.2'nin ertelenmiş kalemi burada kapanır: alan şifrelemesi gerçek bir kolona
(TCKN) bağlanır.

## Kararlar

### 1. Değerler *gözlem* olarak saklanır; `entity` satırı "şu an geçerli olan"dır

`entity_attribute` her değeri kaynağı ve zamanıyla ayrı satır olarak tutar. Bunu tek
kolonla yapmak mümkün değildi: **tutarsızlık tespiti aynı özniteliğin birden çok
gözlemini gerektirir** (müşterinin beyan ettiği adres ile faaliyet belgesindeki adres).
ROADMAP'in *"provenance on every attribute"* koşulu da tam olarak budur.

Sonuç: belgeden/kütükten gelen veri beyanın **üstüne yazılmaz** (`promote_to_current=False`).
Müşterinin ne dediği ile kaynağın ne gösterdiği yan yana durur; fark varsa `discrepancy`
üretilir. Tutarsızlık kapatılmaz, **gerekçesiyle karara bağlanır** — MASAK denetiminde
"bu fark neden kabul edildi" cevapsız kalamaz.

### 2. Belge çıkarımı asla doğrudan kütüğe yazmaz

Docling'in bulduğu her şey `extraction_proposal` satırıdır ve insan onayı bekler (R2'nin
açık koşulu). Reddedilen öneri de silinmez: "belgede bu yazıyordu ama uzman kabul etmedi"
denetimde anlamlı bir kayıttır.

Güven skoru kanıt birikimine dayanır: etiketli + kontrol basamağı tutan bir vergi numarası
0.95, etiketli ama tutmayan 0.50 alır. Eşik altındakiler **atılmaz, düşük güvenle önerilir**
— kaçan bir yönetici adı, yanlış önerilenden pahalıdır (kullanıcı yanlışı tek tıkla
reddeder, eksiği fark etmez).

### 3. Docling opsiyonel kurulumdur

PyTorch dahil ~2 GB'lık ağaç getirir. Zorunlu bağımlılık olsaydı CI her koşuda onu
çözerdi ve API imajı da taşırdı. Kök `pyproject`'te `extraction` bağımlılık grubundadır,
yalnız worker imajına kurulur, `docling_adapter` tembel import eder. Kurulu değilse belge
`skipped` olur — yükleme ve saklama çalışmaya devam eder (R1'in manuel yolu zaten
birincil yollardan biridir).

Asıl kırılgan mantık — Türkçe desen eşleştirme — motordan **ayrı** bir modüldedir
(`documents/extraction.py`) ve Docling olmadan, gerçek belge metinlerine benzeyen
fixture'larla test edilir. Düz metin belgeler motor gerektirmez; uçtan uca akış
(yükleme → çıkarım → öneri → onay → kütük) entegrasyon testinde bu yoldan koşar.

### 4. Kimlik numarası doğrulaması **tavsiyedir, engel değildir**

TCKN/VKN/LEI kontrol basamakları hesaplanır ama kayıt asla reddedilmez; uyarı döner.
Gerekçe: bir uyum aracının, kullanıcının elindeki gerçek belgede yazan numarayı
kaydetmesini engellemesi kabul edilemez. Ayrıca VKN algoritması resmî spesifikasyondan
değil yaygın uygulamalardan alınmıştır; yanılma maliyeti bu tasarımda "gereksiz uyarı"dır,
"veri girilemedi" değil. Aynı kontroller çıkarım hattında **kesinlik filtresi** olarak
çok daha sert kullanılır (etiketsiz bir sayı ancak kontrol basamağı tutarsa önerilir).

TCKN algoritması bilinen doğrulama değeriyle (`10000000146`), LEI ise ISO 17442
(mod-97-10) ile testte sabitlenmiştir. MERSİS'te yalnız biçim kontrol edilir: kontrol
basamağı algoritması teyit edilebilir biçimde yayımlanmadığı için uydurulmuş bir
algoritma gerçek numaraları reddederdi.

### 5. TCKN şifreli + kör indeks; öznitelik satırlarına yalnız maske girer

`entity.national_id` `EncryptedString`tir (ADR-0005). Şifreli değer deterministik
olmadığından "bu TCKN kayıtlı mı" sorusu SQL ile sorulamaz; bunun için ADR-0005'in
öngördüğü **kör indeks** eklendi: `blind_index` = anahtarlı HMAC-SHA256, alan ayrımlı
(`domain`), tekil kısıtla indekslenmiş.

`entity_attribute`, `discrepancy`, `extraction_proposal.evidence_text` ve denetim olayı
payload'ları **şifresizdir**; oralara TCKN'nin yalnız maskesi (son 4 hane) girer. Çıkarım
kanıt metinlerinde geçen geçerli TCKN'ler de maskelenir — aksi hâlde şifreli kolon
anlamsız kalırdı. Vergi/MERSİS numaraları maskelenmez: tüzel kişilerin kamuya açık
tanımlayıcılarıdır ve ER'in deterministik eşleşmesi onlara dayanır.

**Bilinen sınır:** son 4 hanesi aynı olan iki farklı TCKN'de tutarsızlık yakalanmaz.
Kabul edilir; varlık düzeyindeki kör-indeks tekil kısıtı aynı numaranın iki kayda
bağlanmasını zaten engeller.

**Bilinen risk:** kör indeks düşük entropili değerlerde (11 haneli TCKN uzayı sonludur)
sözlük saldırısına açıktır. Bu yüzden parmak izi de en az ciphertext kadar gizli kabul
edilir; güvenliği anahtarın gizliliğine dayanır, uzayın büyüklüğüne değil.

### 6. ER v1: deterministik → çelişki kontrolü → bulanık; otomatik birleştirme yok

Sıra bilinçlidir. En kritik kural **çelişki kontrolü**dür: adı benzeyen ama vergi numarası
farklı olan aday eşleşme sayılmaz. "Yıldız İnşaat" iki ayrı vergi numarasıyla iki ayrı
şirkettir; bulanık eşleşmenin en pahalı hatası (iki farklı müşteriyi birleştirmek) burada
kapanır.

Bulanık eşleştirme `pg_trgm` iledir (R4: embedding değil), **taramayla aynı** Türkçe
normalizasyondan geçmiş ASCII ad üzerinde — böylece "Yıldız İnşaat A.Ş." ile
"YILDIZ INSAAT LTD STI" aynı uzayda buluşur. Tek ve yüksek skorlu aday varsa eşleşme;
birden çok aday ya da orta skor **belirsiz** sayılır ve kullanıcıya sorulur.

Birleştirme kayıt **silmez**: kaynak `merged` işaretlenir, hedefi gösterir, bağlı kayıtlar
(öznitelik, ilişki, belge, tutarsızlık, tarama) hedefe taşınır. Eski bir tarama raporundaki
bağlantı kırılmaz.

### 7. GLEIF: dışarı yalnız LEI kodu çıkar

Invariant 3 taramada mutlaktır (PII asla dış servise gitmez). GLEIF bir tarama servisi
değildir ve LEI kişisel veri değil, şirketin kendi başvurusuyla aldığı kamuya açık bir
tanımlayıcıdır — ROADMAP E0.3 bunu "open data, low risk" sayar. Yine de:

- İstekte **yalnız LEI** gider; ad/adres/vergi no/TCKN gönderilmez (testle sabitlendi).
- Her sorgu `enrichment.lookup` denetim olayı yazar; ne gönderdiğimiz izde durur.
- Kod önce ISO 17442 ile doğrulanır (biçimsiz kod için dış çağrı yapılmaz).
- Sonuç beyanın üstüne yazılmaz; `gleif` kaynaklı gözlem olur ve çelişirse tutarsızlık
  üretir.
- `GLEIF_ENABLED=false` ile tamamen kapatılabilir.

### 8. Ticaret Sicil Gazetesi: kılavuzlu manuel (R1)

E0.3 doğrulaması olmadığı için otomatik gazete sorgusu **yapılmaz**. Kullanıcı gazete
sayısı/tarihi/bağlantısını verir; bunlar `document.source_ref` olarak saklanır ve aynı
çıkarım hattından geçer. Otomatik yol, E0.3 verdict'i geldiğinde tek bir servis
fonksiyonu olarak eklenebilecek şekilde ayrılmıştır (`gazette_source_ref`).

## Sonuçlar

**Olumlu:** Her değerin kaynağı raporlanabilir; tutarsızlık MASAK açısından anlamlı bir
çıktı olarak doğar; belge çıkarımı hız kazandırırken kütüğü kirletmez; ER mükerrer müşteri
kaydını hem formda (yazarken uyarı) hem kabul anında engeller; TCKN artık şifreli.

**Ödünler:**
- Altı yeni tablo; kütük sorguları (dosya sayfası) birden çok çağrı yapıyor. Kabul
  edilebilir: sayfa başına birkaç sorgu, tek kullanıcı-etkileşimli ekran.
- `promote_to_current=False` varsayılanı, kullanıcı beyanı düzeltmek istediğinde ek bir
  adım gerektirir (belgeyi kabul etmek beyanı değiştirmez). Bilinçli: sessiz üzerine
  yazma, tutarsızlık kaydını yok ederdi.
- Docling üretim imajında gerçek belgelerle **henüz doğrulanmadı** (opsiyonel kurulum,
  ağır imaj). Düz metin yolu uçtan uca test edilmiştir; PDF yolu E1.6 dağıtımında pilot
  belgeleriyle sınanacaktır.
- VKN kontrol algoritması resmî spesifikasyona karşı doğrulanmadı (bkz. karar 4).

## Alternatifler

- **Öznitelikleri yalnız `entity` kolonlarında tutmak:** tutarsızlık tespiti imkânsız
  olurdu.
- **Çıkarımı doğrudan kütüğe yazmak:** R2'nin açık koşuluna ve ürünün "karar desteği"
  duruşuna aykırı.
- **Docling'i zorunlu bağımlılık yapmak:** CI ve API imajına ~2 GB; reddedildi.
- **TCKN'yi düz saklayıp yalnız disk şifrelemesine güvenmek:** DB dökümü düz PII taşırdı
  (ADR-0005'in aynı gerekçesi).
- **Embedding tabanlı ER:** R4 gereği ertelendi; etiketli set olmadan ayarlanamaz.

## İlgili

`packages/core/src/aegis_core/entities/` (identifiers · resolution · service · gleif);
`packages/core/src/aegis_core/documents/` (extraction · storage · docling_adapter ·
service); `migrations/versions/0004_entity_registry.py`;
`apps/api/tests/integration/test_entities.py`, `test_documents.py`.
