# ADR-0015: Toplu tarama — CSV, kütük çözümlemesi, parça parça sürdürülebilir işleme

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-01
- **İlgili:** ROADMAP E3.3, Phase 3 çıkış ölçütü 3 (1.000 satır, satır başına durum, doğru kota);
  ADR-0005 (alan şifreleme), ADR-0007 (varlık kütüğü / ER), ADR-0012 (kota)

## Bağlam

Müşterisi çok olan yükümlü (SMMM ofisi, ödeme kuruluşu) listesini tek tek girmez. Toplu taramada
üç tehlike var: aynı müşteriyi ikinci kez açmak, kişisel veriyi korumasız saklamak ve uzun işin
yarıda kalıp kaybolması.

## Kararlar

### 1. Önizleme durumsuz, kayıt yalnız eşlenen alanlarla
`POST /batches/preview` dosyayı saklamaz: başlıklar, önerilen eşleme (Türkçe/İngilizce eş adlar),
ilk 20 satırın doğrulaması. Kayıtta yalnız ad, tür, vergi no, MERSİS, ülke ve müşteri referansı
tutulur. Kodlama UTF-8 ya da Windows-1254 (Türkçe Excel), ayraç `;`, `,` ya da sekme. Sınır
1.000 satır, 2 MB.

### 2. TCKN alınmaz
Kütükte TCKN şifreli saklanır; satır tablosu bu şifrelemeyi taşımaz. TCKN'ye benzeyen sütun eşleme
listesinde gösterilmez ve eşlenmek istenirse dosya reddedilir. Kişiler kimlik numarasıyla varlık
formundan eklenir. Kişi satırları adla taranır (yaptırım listeleri TCKN taşımaz).

### 3. Satır, elle taramayla aynı yoldan geçer
ER (`resolve_entity`): vergi no / MERSİS eşleşirse ya da tek ve güçlü ad eşleşmesi varsa mevcut
varlık; yoksa yeni varlık (`source_ref = batch:<id>#satir-<n>`); **belirsizse satır taranmaz** ve
insana sorulur (aday listesiyle). Sonra `subjects_for_entity` + `run_screening`. Aynı dosyada aynı
vergi no ya da aynı normalize ad + tür ikinci kez taranmaz. Benzer numaralı şube adları ("Ege Firma
1/2/3") ER'nin tasarımı gereği belirsiz düşer; bu bilinçli bir maliyettir.

### 4. Parça parça, satır başına alt işlem, sürdürülebilir
Worker 25'lik parçalar işler, her parça ayrı transaction'da commit edilir; satırlar
`FOR UPDATE SKIP LOCKED` ile alınır (worker ile "şimdi işle" çakışmaz). Satırın hatası diğerlerini
durdurmaz; motor yoksa satır `failed` ("yeniden denenebilir") olur, 3 denemeye kadar yeniden
kuyruğa alınır ve açılmış varlık yeniden açılmaz. API görevi commit'ten önce kuyruğa bıraktığı için
görev toplu işi göremezse kısa aralıkla yeniden dener. Kuyruğa ulaşılamazsa iş `queued` kalır.

### 5. Kota başlatırken, kullanım taramadan
Başlatmada bekleyen satır sayısı kotayla denetlenir (her satır en az bir sorgu); aşım izni olmayan
planda iş başlamaz (402), taslak kalır. Gerçek kullanım, her satırın taramasının özne sayısıyla
mevcut sayaçtan gelir (`requested_by_user_id` toplu işi başlatan kişidir).

### 6. Sonuç riske göre sıralı, toplu eylem iki tane
Sıralama anahtarı: yaptırım > PEP > yüksek skorlu aday > en yüksek skor. Toplu eylemler: izlemeye al
(plan sınırıyla) ve vaka aç (yaptırım → kritik + EDD, PEP → yüksek). CSV özet Excel'in doğrudan
açtığı biçimde (UTF-8 BOM, `;`), formül enjeksiyonuna karşı `= + - @` ile başlayan hücreler metin.

## Doğrulama

Birim 10 (çözme, ayraç, eşleme, TCKN, tekrar, sınırlar, sıralama, formül), entegrasyon 4: uçtan uca
(ER eşleşme/yeni/belirsiz, parça parça, insan kararı, toplu vaka/izleme, CSV, denetim, RLS), TCKN
reddi + kota, motor kesintisi + yeniden deneme, worker koroutini (parça commit, görünmezse yeniden
dene). 7 koruma tek tek kaldırıldığında testler düştü.
