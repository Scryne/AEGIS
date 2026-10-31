# ADR-0012: Plan ve kota — elle yetkilendirme, kayıttan sayım, özne başına sorgu

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-01
- **İlgili:** ROADMAP E2.6 (R5: pilot → ücretli geçiş), E3.5 (faturalama otomasyonu);
  ADR-0002 (kontrol düzlemi / RLS ayrımı), ADR-0007 (izleme-lite)

## Bağlam

E2.6, pilotları ücretli müşteriye çevirir. Yol haritası bunun için ödeme altyapısı değil,
**elle yetkilendirme** ister: kiracı başına plan alanı ve kota denetimi; ölçüm altyapısı E3.5'e
kalır. Ödeme kanalı (iyzico/PayTR bağlantısı ya da elle fatura), sözleşme ve fiyat ticari kararlardır
ve bu ADR'nin dışındadır.

## Kararlar

### 1. Plan kontrol düzleminde, katalog kodda
`organization.plan_code` (göç 0010, `CHECK` ile üç değer) ve `plan_started_on`. `organization`
RLS'siz kontrol düzlemi tablosudur; plan oturum açmadan önce de okunabilir. Katalog
`aegis_core/billing/plans.py`'de sabittir: pilot, standart, kurumsal. Atama
`scripts/plan_ata.py` ile ayrıcalıklı bağlantıdan yapılır. Reddedilen: kiracı ayarı
(`tenant_setting`) — kiracı kendi planını değiştirebilecek bir tabloya plan yazılmaz.

### 2. Fiyat kodda yok
Katalog yalnız işin miktarını bilir (aylık dahil sorgu, izleme varlık sınırı, aşım izni). Fiyat
Phase 0 sinyallerine dayanan ticari karardır ve sözleşmede yaşar; sayıları Scryne değiştirir.
v1 varsayılanları: pilot 300 sorgu / 25 izleme / aşım yok; standart 1.500 / 150 / aşım var;
kurumsal 6.000 / 1.000 / aşım var.

### 3. Sorgu = taranan özne, dönem = Türkiye takvim ayı
Bir tarama şirketi ve bağlı kişilerini birlikte tarar; maliyet (yente sorgusu) ve değer özne
başınadır. Kullanım, dönem içindeki **kullanıcı tarafından başlatılmış** taramaların
`jsonb_array_length(subjects)` toplamıdır; ayrı sayaç tablosu yoktur (E3.5'e kadar). Gece izlemesi
koşuları (`requested_by_user_id` boş) sayılmaz: izleme ayrı bir kapasite olarak satılır. Başarısız
koşular sayılır (sorgu listeye gitti). Dönem `Europe/Istanbul` takvim ayıdır; UTC ayı, Türkiye'de
gece 00:00–03:00 arasında yapılan taramayı önceki aya yazardı.

### 4. Kapı taramadan önce, kiracı satırı kilitli
Senkron, varlık ve derin tarama uçları taramadan önce `require_screening_quota` çağırır. Aşım
izni olmayan planda isteğin tamamı kotayı aşıyorsa 402 `quota_exceeded`; kısmi tarama yapılmaz.
Kiracının `organization` satırı `FOR UPDATE` ile kilitlenir, eşzamanlı iki istek aynı son
sorguları ikişer kez harcayamaz. Aşım izni olan planda tarama sürer, aşım ekranda ayrı görünür ve
elle faturalanır.

### 5. İzleme sınırı açarken
Bir varlığı izlemeye almak sınır doluysa 409 `plan_limit`; izlemeden çıkarmak her zaman serbest.
Zaten izlenen varlığı yeniden "izle" demek sınırı yeniden saymaz.

## Sonuçlar

- `GET /api/v1/billing/usage`: plan, dönem, kullanılan / kalan / aşım, izlenen varlık, `blocked`.
- Web: "Plan ve kullanım" sayfası (sahip, uyum görevlisi, denetçi), kota dolunca uyarı.
- Testler: özne sayımı ve 402 (kısmi tarama yok), plan yükseltmede aşımın ayrı sayılması, izleme
  sınırı ve gece koşularının sayılmaması; dönemin İstanbul ayı olduğu birim testi. Kota kapısı
  mutasyonla kaldırılınca test düşüyor.
- Açık (Scryne): fiyat, ödeme kanalı, abonelik sözleşmesi, pilot dönüşümü, vaka çalışması.
