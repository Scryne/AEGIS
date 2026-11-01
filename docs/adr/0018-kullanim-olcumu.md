# ADR-0018: Kullanım ölçümü ve ay sonu dökümü — fiyatsız iskelet

- **Durum:** Kabul edildi (iskelet; ödeme tarafı açık)
- **Tarih:** 2026-11-01
- **İlgili:** ROADMAP E3.5, Phase 3 çıkış ölçütü 3–4; ADR-0012 (plan ve kota), ADR-0015, ADR-0016

## Bağlam

E3.5 "faturalama otomasyonu"nun iki yarısı var: **ne kadar iş yapıldı** (ölçüm) ve **ne kadar tutar,
nasıl tahsil edilir** (fiyat, ödeme kanalı, sözleşme, tahsilat takibi). İkinci yarı ticari karardır
(ADR-0012: fiyat sözleşmede yaşar; ödeme kanalı iyzico/PayTR seçimi yapılmadı). Bu ADR yalnız ilk
yarıyı kapatır.

## Kararlar

1. **Kaynağa göre döküm.** Sorgu (taranan özne) ekran / API anahtarı / toplu tarama olarak ayrılır;
   toplam, kota sayacıyla birebir aynıdır. Toplu taramada taranan satır sayısı ayrıca gösterilir.
2. **Yapılamayan tarama hak tüketmez.** Motora ulaşılamadığı için `failed` kalan tarama ne kotaya ne
   dökümüne girer. Önceden (E2.6) sayılıyordu; toplu işin yeniden denemesi bunu görünür kıldı: aynı
   satır motor kesintisinde iki kez sayılıyordu. Kota sayacı ve döküm aynı süzgeci kullanır.
3. **Uyarı düzeyi.** `ok` · `near` (dahil kotanın %80'i) · `exhausted` (aşım izni yok, durdu) ·
   `overage` (aşım izinli planda aşımda). Plan sayfası `near`da uyarır. Sert durdurma yalnız aşım izni
   olmayan planda ve hiçbir zaman kısmi tarama olarak değil (402, mevcut davranış).
4. **Ay sonu dökümü donar.** Worker her gün 03:15 UTC'de önceki İstanbul takvim ayını, kapanmamışsa
   `usage_statement`a yazar (kiracı ve dönem başına tek satır; RLS). Kapanmış döküm sonradan değişmez.

## Açık (ticari karar, Scryne)

Fiyat ve aşım birim ücreti, izleme eklentisi ücreti, ödeme sağlayıcısı (abonelik ya da fatura),
tahsilat takibi (dunning) ve gelir panosu. Döküm satırı bunların girdisidir; tutar hesabı eklenince
`usage_statement`tan okunur.

## Doğrulama

Entegrasyon: ekran 1 + API 1 + toplu 2 = 4 sorgu, motor kesintisindeki tarama sayılmaz, dönem kapanışı
idempotent, RBAC ve izolasyon; uyarı düzeyleri. Süzgeç kaldırılınca test düşüyor. Canlı (aegis_dev):
Ekim dönemi kapandı, Kasım dökümü 6 sorgunun 6'sını toplu taramaya bağlıyor (düzeltmeden önce 12
görünüyordu: 6'sı başarısız denemeydi).
