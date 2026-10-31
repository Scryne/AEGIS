# ADR-0010: Açıklanabilir risk puanı — sabit ağırlıklı faktör modeli, kayda geçen zaman çizelgesi

- **Durum:** Kabul edildi
- **Tarih:** 2026-10-31
- **Karar veren:** Scryne (geliştirme devri)
- **İlgili:** ROADMAP §8 E2.3; ADR-0008 (kural tabanlı seviye; puan Phase 2'ye bırakılmıştı);
  ADR-0009 (UBO); Ürün Planı §6.6 (LLM çıktısı doğrudan puanlamaz)

## Bağlam

ADR-0008 risk *seviyesini* kural olarak tanımladı ve 0–100 puanı bilinçli olarak erteledi:
"bu dosyaya neden 72 dediniz" sorusu cevaplanamazdı. E2.3 puanı istiyor, ama aynı ölçütle:
her faktör gerekçe ve dayanak taşımalı.

## Kararlar

1. **Puan = faktör toplamı.** `reports/score.py` saf bir fonksiyondur; girdisi ADR-0008'in kural
   bulguları + son UBO hesabının durumu + varlığın yargı alanıdır. Çıktı faktör listesidir
   (kod, etiket, puan, tekrar sayısı, gerekçe, dayanak kayıtlar); puan bu satırların toplamıdır
   (0–100 kırpılır).
2. **Ağırlıklar sabit ve sürümlüdür (v1).** Onaylanmış yaptırım 60, PEP 25, diğer onaylı eşleşme 15,
   bekleyen işaretli eşleşme 8 (tavan 16), bekleyen eşleşme 2 (tavan 6), açık kritik tutarsızlık 15
   (tavan 30), açık tutarsızlık 5 (tavan 10), başarısız tarama 10, tarama yok 15, UBO belirlenemedi
   20, UBO eşiği aşan yok 10, döngüsel ortaklık 5, UBO hesabı yok 10, yabancı yargı alanı 5,
   yüksek riskli yargı alanı 20. Bantlar: 0–24 düşük, 25–49 orta, 50+ yüksek. Kiracı bazında ayar
   müşteri isteyene kadar yoktur; ağırlık değişirse `WEIGHTS_VERSION` değişir.
3. **Onaylanmış yaptırım bandı her zaman yüksek yapar**; toplamın altında kalan bir yaptırım
   "orta" okunamaz.
4. **Bekleyen bulgu puana küçük pay katar ve dökümü "tamamlanmadı" yapar**; seviyedeki duruşla
   aynı (ADR-0008 §2): motor skorlar, insan karar verir.
5. **Yüksek riskli ülke listesi koddan değil yapılandırmadan gelir** (`HIGH_RISK_COUNTRIES`,
   boş başlar). Liste kurumun uyum politikasıdır ve güncel FATF listesiyle kurum tarafından
   girilir; koda gömülü tarihli bir liste sessizce bayatlardı.
6. **Canlı puan yazmaz; kayda geçirme ayrı bir eylemdir.** `GET /reports/score/{id}` her okumada
   yeniden hesaplar ve hiçbir şey yazmaz (denetçi de görür). `POST …/snapshot` dökümü
   `risk_score_snapshot` tablosuna (RLS, saklama) yazar ve `risk_score.snapshot` denetim olayı üretir;
   döküm son kayıtla aynıysa yeni satır yazılmaz. UBO hesabı (kütüğü etkileyen eylem) değişen
   puanı kendisi kayda geçirir. Zaman çizelgesi böylece yalnız değişimleri ve kimin kaydettiğini
   taşır.

## Sonuçlar

- Puan, seviyenin yerine geçmez: seviye "neden bu kademe", puan "ne kadar ve hangi faktörlerden".
- Olumsuz haber (E2.5) E3.6'daki kesinlik ölçümüne kadar puan dışıdır.
- Dosya raporuna (PDF/Word) puan dökümü sayfası henüz eklenmedi (E2.3'ün açık kalemi).
