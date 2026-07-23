# Veri İşleme Sözleşmesi (DPA) — Şablon (v1)

> ⚠️ **v1 TASLAK — hukuki inceleme gerekir.** KVKK (6698) m.12 ve ilgili mevzuat esas
> alınmıştır; imzadan önce avukat onayı alınmalı, `{{...}}` doldurulmalıdır.

**Taraflar**
- **Veri Sorumlusu ("Müşteri"):** {{MUSTERI_UNVANI}}, {{MUSTERI_ADRES}}
- **Veri İşleyen ("AEGIS"):** {{ŞİRKET_UNVANI}}, {{ADRES}}

Bu DPA, Taraflar arasındaki {{ANA_SOZLESME}} ("Ana Sözleşme") kapsamında AEGIS'in Müşteri
adına kişisel veri işlemesini düzenler. Çelişki halinde KVKK amir hükümleri önce gelir.

## 1. Tanımlar
KVKK'daki tanımlar geçerlidir: kişisel veri, işleme, veri sorumlusu, veri işleyen, ilgili
kişi, açık rıza, imha (silme/yok etme/anonimleştirme).

## 2. İşlemenin Konusu ve Süresi
- **Konu/nitelik:** KYB/kurumsal due diligence; şirket profili doğrulama ve
  yaptırım/PEP/watchlist tarama.
- **Amaç:** Müşterinin MASAK (5549) ve KYB yükümlülüklerini yerine getirmesine destek.
- **Süre:** Ana Sözleşme süresi + mevzuat saklama süresi (≥{{SAKLAMA_YILI}} yıl).
- **Veri kategorileri / ilgili kişiler:** taranan gerçek/tüzel kişiler; kimlik/ticari
  veriler, tarama sonuçları, yüklenen belgeler (bkz. envanter tablo B).

## 3. AEGIS'in (İşleyen) Yükümlülükleri
1. Kişisel veriyi **yalnızca Müşterinin belgelenmiş talimatı** doğrultusunda işler; aksi
   bir hukuki yükümlülük doğarsa (izin verildiği ölçüde) önceden bildirir.
2. **Veri yerelliği:** Veriyi Türkiye'deki altyapıda işler; **yurt dışına aktarmaz**
   (KVKK m.9). Tarama self-host yente ile yapılır; PII dış tarama API'lerine gönderilmez.
   Faz 1'de LLM/dış AI çağrısı yoktur.
3. **Gizlilik:** Erişen personel gizlilikle yükümlüdür; erişim rol-bazlıdır (RBAC).
4. **Güvenlik tedbirleri (m.12):**
   - Kiracı-başına DB-düzeyi izolasyon (RLS, fail-closed),
   - Append-only, tamper-evident denetim izi (hash zinciri),
   - Hassas kolonlarda AES-256-GCM şifreleme; iletimde TLS; at-rest disk şifreleme,
   - Sır yönetimi (anahtarlar git dışında), yedekleme + restore tatbikatı.
5. **Alt-işleyen:** Yalnızca zorunlu altyapı (barındırma) için, denk güvence içeren
   sözleşmeyle ve Müşteriyi bilgilendirerek alt-işleyen kullanır ({{ALT_ISLEYEN}}).
6. **İlgili kişi talepleri:** Müşteriye yönelen taleplerin karşılanmasında teknik olarak
   yardımcı olur (erişim/düzeltme/silme; dışa aktarma).
7. **İhlal bildirimi:** Bir kişisel veri ihlalini öğrenmesinden itibaren **gecikmeksizin**
   Müşteriye bildirir; Kurul'a/ilgili kişiye bildirim Müşteri (sorumlu) sorumluluğundadır,
   AEGIS gerekli bilgiyle destekler.
8. **İmha/iade:** İlişki sonunda, mevzuat saklama süreleri saklı kalmak kaydıyla, kişisel
   veriyi Müşterinin tercihine göre iade eder veya imha eder (silme/yok etme).
9. **Denetim:** Müşteriye, makul aralıklarla ve gizlilik içinde, uyumu doğrulama imkânı
   (rapor/denetim izi) sağlar.

## 4. Müşterinin (Sorumlu) Yükümlülükleri
- İşlemenin **hukuki sebebini** (KVKK m.5/6) tayin eder ve **aydınlatma** yükümlülüğünü
  yerine getirir (ilgili kişilere karşı).
- AEGIS'e verdiği talimatların ve yüklediği verinin hukuka uygunluğundan sorumludur.
- MASAK yükümlülükleri (ŞİB dahil) ve **nihai uyum kararı** Müşteriye aittir
  (bkz. pilot/abonelik sözleşmesindeki karar-destek maddesi).

## 5. Sorumluluk
Her Taraf kendi KVKK yükümlülüklerinin ihlalinden sorumludur. AEGIS'in sorumluluğu Ana
Sözleşmedeki sınırlara tabidir; karar-destek konumlandırması (AEGIS uyum kararını **vermez**)
saklıdır.

**İmza — Müşteri:** {{IMZA}} · **İmza — AEGIS:** {{IMZA}} · **Tarih:** {{TARIH}} · **Sürüm:** v1 (taslak)
