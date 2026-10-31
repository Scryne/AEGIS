# ADR-0011: ŞİB taslağı — rehbere bağlı form, yargı alanları boş, gizlilik ve şifreli saklama

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-01
- **İlgili:** ROADMAP E2.2; CLAUDE.md Invariant 1 (RLS), 2 (denetim izi), 4 (saklama);
  ADR-0005 (alan şifreleme), ADR-0008 (raporlama), ADR-0009 (gerçek faydalanıcı)

## Bağlam

E2.2, uyum görevlisinin MASAK Online'a gireceği şüpheli işlem bildirimini (ŞİB) dosyadan
hazırlar. Bu, ürünün ödenen değerlerinden biridir (R5) ama en riskli çıktısıdır: yanlış
alanla hazırlanmış bir taslak "çalışıyor görünüp" yanlış güven verir. Bu yüzden 2026-10-31'de
alanlar resmî kaynaktan teyit edilmeden yazılmadı.

## Kararlar

### 1. Form yapısı birincil kaynaktan, sürümüyle
Alanlar MASAK'ın *SM/SMMM/YMM Şüpheli İşlem Bildirim Rehberi* MSK-RHB-ŞİB-018-1.0'dan
(16.06.2025, §4.2: A–G bölümleri) ve *Şüphe Kategorileri Referans Tablosu*ndan (41 kod) harfiyen
alındı (`aegis_core/sib/kodlar.py`). Çapa segment SMMM/YMM olduğu için bu rehber; bankaların
formunda hesap bölümü vardır, başka gruba açılırken rehber ayrı sürüm olarak eklenir. Her
taslak hangi rehber sürümüyle hazırlandığını taşır (`guide_version`).

### 2. Kurallar: rehberde "zorunlu" yazan hata, "gerekmektedir" yazan uyarı
Hata (dışa aktarmayı engeller): kategori; terörizmde örgüt türü ve SK-23/SK-35, KİS'te SK-36;
1–3 SK kodu; ek bildirimde önceki referans no; açıklama 300–50.000 karakter; kişilerde bağlantı
türü, ad-soyad, unvan, kuruluş nev'i; işlemde tarih, tutar, coğrafi konum, teşebbüs = tek işlem.
Uyarı (engellemez): TCKN sağlaması (kütük kuralı: kaydedilene saygı), adres, yabancı paranın TL
karşılığı. MASAK Online'ın alan bazlı doğrulamaları herkese açık değil; rehberde yazmayan bir
zorunluluk uydurulmadı.

### 3. Ön doldurma olgu taşır, yargı taşımaz
Kütükten kimlik, gerçek faydalanıcı hesabından UBO'lar (%pay ek bilgide), dosyanın risk
bulgularından açıklama için madde listesi gelir. **Bildirim kategorisi, şüphe kategorisi,
aciliyet ve şüpheli işlemler seçilmez**: bunlar yükümlünün kararıdır; ürünün önermesi kararı
kaydırır. Açıklama bir iskelettir: yönerge satırı ve `[…]` yer tutucuları vardır, metin
değiştirilmeden (boşluk farkı sayılmaz) dışa aktarılamaz — rehber "sürekli benzer metin" yerine
her bildirim için özgün açıklama ister.

### 4. Gizlilik ve saklama
Bildirimin varlığı bile gizlidir (5549 s.K. m.4/2): uçlar ve ekranlar yalnız `owner` ve
`compliance_officer`; analist ve denetçi listeyi de göremez (403). Form tek şifreli kolondadır
(TCKN, adres, anne/baba adı); düz kolonlar kişisel veri taşımaz. Denetim izi oluşturma,
düzenleme, dışa aktarma ve iptali yazar, **içeriği yazmaz**. Taslak silinmez; gerekçeyle iptal
edilir ve ≥5 yıl saklanır. Word belgesinin üst/alt bilgisinde gizlilik ibaresi, gövdede taslak
ve sorumluluk notu vardır; indirme `Cache-Control: no-store` ile döner.

### 5. Çıktı Word (düzenlenebilir)
Belge formun sırasını ve rehberin alan adlarını izler; seçmeli değerler kodla değil etiketle
yazılır. Dışa aktarılmış taslak yeniden düzenlenirse durumu `taslak`a döner.

## Sonuçlar
- (+) 17 birim + 5 entegrasyon testi; mutasyonların 5'i de yakalandı (hatalıyken dışa aktarma,
  düz metin saklama, denetim izinde içerik, analist erişimi, iptal edileni düzenleme).
- (+) Gerçek API + web ile uçtan uca: taslak açma, düzenleme, kaydetme, Word indirme; 1440/390
  taşmasız.
- (−) Pilot uyum görevlileriyle gerçek bir bildirime karşı doğrulama (ROADMAP E2.2 son maddesi)
  yapılmadı; pilot gerektirir.
- (−) Bildirim süresi (şüphenin oluştuğu tarihten itibaren 10 iş günü) yalnız ikincil kaynakta
  teyitli; süre sayacı bu yüzden eklenmedi.
