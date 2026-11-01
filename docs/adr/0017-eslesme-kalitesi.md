# ADR-0017: Eşleşme kalitesi programı — insan kararından ölçüm, öneri olarak eşik

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-01
- **İlgili:** ROADMAP E3.6, R4 (embedding kararı veriye bağlı), Phase 3 çıkış ölçütü 5; E1.3 recall kapısı

## Kararlar

### 1. Etiket deposu ayrı tablo değil
İnsan kararları zaten `match_candidate`da (karar, otomatik mi, skor). Ölçüm doğrudan buradan okunur;
her yeni karar (özellikle elenen yanlış pozitif) bir sonraki ölçüme kendiliğinden girer. Ayrı bir
etiket tablosu aynı bilgiyi iki yerde tutardı.

### 2. Otomatik elenenin doğrusu bilinmez
Motorun elediği adayı insan görmedi; ölçüme katılmaz, sayısı ayrıca gösterilir. Bu yöntem otomatik
eleme bandında kaçan gerçek eşleşmeyi göremez; o, E1.3'ün recall kapısının (Türkçe eval seti, %100
taban) işidir. İki ölçüm birbirinin yerine geçmez.

### 3. Eşik bir öneridir, değişikliği insan yapar
Tarama her aday eşikte "kaç inceleme azalır, kaç onaylı eşleşme kaybolur" gösterir. Öneri, onaylı en
düşük skorun 0,05 altı (ve işaret eşiğinin altında); en az 30 insan kararı yoksa öneri verilmez.
Eşiği uyum uzmanı ayarlardan değiştirir; o değişiklik kendi denetim olayını yazar.

### 4. Eğilim kaydı
`match_eval_run` (RLS) metriklerin donmuş kopyasıdır: haftalık worker (Pazartesi 04:00 UTC) ve elle
"ölçümü kayda geçir" (ör. eşik değişikliğinden önce/sonra). Çıkış ölçütündeki "en az iki ayar turunda
düşüş" bu satırlardan okunur.

### 5. Olumsuz haber ve embedding kapısı
Olumsuz haber betasının ilgili payı ve olumsuz terim ipucunun isabeti ölçülür. Puana alınma için ön
koşul (≥ 100 incelenmiş haber, ≥ %80 ilgili) ekranda gösterilir; karar insanındır. Embedding tabanlı
aday üretimi (R4 kapısı) bu fazda eklenmedi: kararı verecek veri (deterministik + bulanık eşleştirmenin
kaçırdığı gerçek eşleşmeler) henüz yok; ölçüm bu verinin birikeceği yerdir.

## Doğrulama

Birim 7 (oranlar, boş küme, tarama, öneri asla onaylıyı kaybetmez, işaret eşiği tavanı, yetersiz
etiket, olumsuz haber), entegrasyon 2 (karar → ölçüm → kayıt → eğilim, geri besleme, RBAC, izolasyon;
haftalık worker). Canlı (aegis_dev): 6 demo kararıyla sayfa, tarama grafiği ve eğilim tablosu;
1440/390 taşma ve konsol hatası yok.
