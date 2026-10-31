# ADR-0013: Olumsuz haber betası — toplama + elle ayıklama, puan dışı

- **Durum:** Kabul edildi (beta, bayraklı)
- **Tarih:** 2026-11-01
- **İlgili:** ROADMAP E2.5, R8 (zaman kutusu, bayrak, puan dışı), E3.6 (isabet programı);
  CLAUDE.md Invariant 1 (RLS), 2 (denetim izi)

## Bağlam

E2.5, varlık hakkında olumsuz haber taramasıdır. R8 bunu zaman kutulu, bayraklı bir beta yapar ve
şunu der: süre taşarsa **toplama + elle ayıklama** gönderilir, LLM hattı (kimlik ayrımı →
olumsuzluk sınıflaması → kanıt cümlesi) Phase 3'e geçer. E0.3 haber kaynağı taraması yapılmamıştı.

## Kararlar

### 1. Kaynak: Google News RSS (tr-TR)
2026-11-01 denemesi: anahtarsız, kamuya mal olmuş bir isimde 30+ sonuç, ulusal ve yerel yayıncılar
(BBC Türkçe, DW, Bianet, bölge gazeteleri). GDELT DOC 2.0 aynı gün bu ağdan sürekli "5 sn'de bir"
sınırına takıldı; ikinci kaynak `NewsProvider` arayüzünün arkasına sonradan eklenir. Yalnız başlık,
yayıncı, bağlantı ve tarih okunur; haber metni indirilmez ve saklanmaz. XML `defusedxml` ile
ayrıştırılır; istek sabit bir ana bilgisayara gider.

### 2. İki sorgu
Şirket adından hukuki ekler (A.Ş., Ltd. Şti., San. ve Tic. …) atılır. Biri adın kendisi (güncel
haber), biri ad + olumsuz terim grubu (`dolandırıcılık OR gözaltı OR …`, hedefli). Sonuçlar
bağlantı özetiyle tekilleşir (`uq(tenant, entity, url_hash)`); yeniden tarama yalnız yenileri ekler.
Bir sorgunun düşmesi diğerini durdurmaz, ekran bunu söyler.

### 3. Olumsuz terim ipucu, karar değil
Başlıkta geçen kök terimler (Türkçe küçük harfle) adayın yanında gösterilir ve sıralamayı belirler.
Haberin bu kişi hakkında olup olmadığına (aynı adlı başka biri) insan karar verir: "ilgili" ya da
"ilgisiz", en az 10 karakterlik gerekçeyle, denetim izine yazılır. Adaylar ve kararlar **risk
puanına girmez** (E3.6 isabet ölçümüne kadar).

### 4. Bayrak ve koruma
Kiracı ayarı `adverse_media_beta`; açıp kapatmak sahibin işidir ve denetlenir. Kapalıyken tarama 409
ve dış kaynağa istek gitmez. Aynı varlık 5 dakika içinde yeniden taranamaz (429 + `Retry-After`).

### 5. LLM hattı ertelendi (R8)
Kimlik ayrımı ve olumsuzluk sınıflaması anlam kararlarıdır; Scryne'ın sisteminde varsayılan aday
TypeSafe'tir (sınıflama, doğrulama). Etiketli değerlendirme seti (~50 pilot vakası) olmadan eşik
seçilemez; bu yüzden Phase 3'e, E3.6 ile birlikte bırakıldı.

## Sonuçlar

- `adverse_media_item` (göç 0011, RLS, izolasyon kapısında). Uçlar: `GET/PUT /adverse-media/beta`,
  `GET /entities/{id}/adverse-media`, `POST /entities/{id}/adverse-media/scan`,
  `POST /adverse-media/{id}/review`.
- Web: varlık sayfasında "Olumsuz haber (beta)" bölümü; Plan ve Kullanım sayfasında sahip anahtarı.
- Testler: RSS ayrıştırma (yayıncı eki, bozuk öğe, varlık bombası reddi), sorgu kurma, Türkçe büyük
  harfte terim eşleşmesi; bayrak, tekilleşme, gerekçe zorunluluğu, oran sınırı, kısmi kaynak
  hatası. Beta kapısı mutasyonla kaldırılınca test düşüyor.
- Testte bulunan gerçek hata: User-Agent başlığındaki Türkçe karakter uygulama açılışını
  düşürüyordu (httpx başlıkları ASCII ister).
