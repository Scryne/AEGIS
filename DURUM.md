# DURUM — AEGIS — MASAK/KYB due diligence

> **Ne bu dosya:** sertifika değil **envanter**. Ölçülen gerçek durum; "çalışmıyor" yazan satır
> kusur değil, kayıt. Kapanış standardı: `ScryneOS/🎯 100-Command-Center/Kapanis-Standardi.md`

**Ölçüm tarihi:** 2026-09-26 (önceki: 2026-08-27)
**Tek cümle:** İlk kez uçtan uca çalıştırıldı (API + Celery worker + Docling + yente + web);
259 birim + 79 izolasyon/entegrasyon + 36 uçtan uca recall testi yeşil, bağımlılık açığı 0.

## Ne çalışıyor (ölçüldü)

- **Testler:** birim + normalizasyon recall tabanı 259 · kiracı izolasyon kapısı + API
  entegrasyonu (testcontainers) 79 · gerçek yente/Elasticsearch üzerinden recall 36/36.
  ruff, mypy (strict), web lint/tsc/build temiz.
- **Güvenlik:** `pip-audit` 0, `pnpm audit` (tümü) 0, gitleaks temiz.
- **Uçtan uca demo** (`scripts/demo_verisi.py`, kurgusal): 3 KYB vakası — temiz şirket (yönetici +
  gerçek faydalanıcı + imza sirküleri PDF → Docling → 3 doğru öneri), doğrulanan eşleşme,
  gerekçeyle elenen eşadlı; 2 PDF dosya raporu, 21 denetim olayı, hash zinciri doğrulandı.
- **Arayüz:** 13 ekran × masaüstü/mobil, 26/26 yatay taşmasız ve konsol hatasız.

## 2026-09-26 denetiminde kapatılanlar

1. **CI 08-08'den beri kırmızıydı:** gitleaks bir test fikstürü anahtarını sır sanıyordu
   (yalnız `conftest.py`'de, geçmiş dahil doğrulandı) → gerekçeli `.gitleaksignore`.
2. **Bağımlılıklar:** Next 16.0'da 2 kritik (Image Optimizer'da kimlik doğrulamasız RCE dahil) +
   11 yüksek üretim açığı; cryptography + pypdf'te 5 açık. CI'daki `pip-audit` `|| true` ile hiç
   kırılmıyordu, npm denetimi yoktu → ikisi de bloke edici.
3. **Belge çıkarımı yanlış kişiye yanlış TCKN bağlıyordu:** Docling satırları paragrafta birleştiriyor;
   ikinci yetkiliye birincinin TCKN'si ve yetki ifadesi gidiyordu, unvan satırı kişi önerisi
   üretiyordu → satır yapısı geri kurulur, TCKN önce kişinin kendi satırında aranır (4 test).
4. **Öneri gövdesinde TCKN düz metin duruyordu** (ADR-0007 §5'e aykırı) → şifreli token + maske;
   eski satırlar okunur; veritabanı düzeyinde test.
5. **Başarısız/atlanmış çıkarım hiç yeniden denenemiyordu** (görev idempotent) → `POST
   /documents/{id}/extract` + denetim olayı + arayüz butonu (4 test).
6. **Elenen yüksek skorlu aday** taramayı sonsuza dek "acil inceleme"de tutuyordu → `flagged_pending`.
7. **Windows'ta worker hiç görev işleyemiyordu** (Proactor döngüsü) → Selector politikası; README'ye
   Windows notları (beat, `TORCHDYNAMO_DISABLE`).
8. Dev ortamında biçimi yanlış şifreleme anahtarı ham 500'e dönüşüyordu → açılışta doğrulama;
   `.env`'e bağlı düşen şifreleme testi hermetik.
9. **Arayüz:** mobilde her sayfa taşıyordu (kabuk) + ham eşik JSON'u; menüde aktif sayfa yoktu;
   Panel yalnız üye listesiydi → iş kuyruğu panosu; tanıtım sayfası tek başlıktı; kararlı adayda
   aynı kararın butonu. DESIGN.md oluşturuldu (lint 0 hata).

## Ne yarım / bilinçli açık

- E1.6 (production deploy, TLS, şifreli hacimler, pilot) açık.
- Docling PDF yolu üretilmiş belgeyle doğrulandı; **gerçek pilot belgeleri** hâlâ gerekli. VKN
  kontrol basamağı resmî spesifikasyona karşı doğrulanmadı.
- MASAK kaynak dosya düzeni ve `aegis_all` birleşik kapsamı canlı kurulumda teyit edilecek.
