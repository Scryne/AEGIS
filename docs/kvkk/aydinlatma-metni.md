# Aydınlatma Metni — AEGIS Platform Kullanıcıları

> ⚠️ **v1 TASLAK — hukuki inceleme gerekir.** `{{...}}` yer tutucuları doldurulmalı;
> yürürlükten önce KVKK uzmanı/avukat onayı alınmalıdır.

**Kapsam:** Bu metin, AEGIS platformuna **kullanıcı olarak** (ofis sahibi/çalışanı;
owner, uyum uzmanı, analist, denetçi) kayıt olan gerçek kişilerin kişisel verilerinin
işlenmesini kapsar. Müşterinin AEGIS üzerinde işlediği **taranan üçüncü kişilere** ait
verilerde AEGIS *veri işleyendir*; o veriler için aydınlatma yükümlülüğü müşteriye
(veri sorumlusuna) aittir (bkz. DPA).

## 1. Veri Sorumlusu
6698 sayılı Kişisel Verilerin Korunması Kanunu ("KVKK") uyarınca veri sorumlusu:
- **Unvan:** {{ŞİRKET_UNVANI}}
- **Adres:** {{ADRES}}
- **MERSIS/Vergi No:** {{MERSIS_NO}} / {{VERGI_NO}}
- **İrtibat / KEP:** {{E_POSTA}} / {{KEP_ADRESI}}

## 2. İşlenen Kişisel Veriler
| Veri kategorisi | Örnek veriler | Kaynak |
|---|---|---|
| Kimlik | Ad, soyad | Kullanıcı kaydı |
| İletişim | E-posta adresi | Kullanıcı kaydı |
| İşlem güvenliği | Parola özeti (Argon2), oturum/token bilgisi, rol | Sistem üretir |
| Denetim/log | İşlem kayıtları (IP, request-id, zaman damgası, yapılan eylem) | Sistem üretir |

> Not: Parolalar **düz metin saklanmaz** (Argon2 ile özetlenir). Erişim token'ı
> httpOnly çerezde tutulur; tarayıcı token'ı görmez.

## 3. İşleme Amaçları
- Hesap oluşturma, kimlik doğrulama ve yetkilendirme (RBAC),
- Hizmetin sunulması, kiracı (ofis) bazlı erişim ve izolasyonun sağlanması,
- Bilgi güvenliği, kötüye kullanım/brute-force önleme (oran sınırlama),
- Yasal yükümlülükler ve denetlenebilirlik için işlem kayıtlarının tutulması,
- Destek taleplerinin karşılanması ve hizmet iyileştirme.

## 4. Hukuki Sebepler (KVKK m.5)
- **Sözleşmenin kurulması/ifası** (m.5/2-c): hesap ve hizmet sunumu için gerekli veriler,
- **Hukuki yükümlülük** (m.5/2-ç): denetim izi ve saklama yükümlülükleri,
- **Meşru menfaat** (m.5/2-f): bilgi güvenliği, kötüye kullanım önleme (temel hak ve
  özgürlüklere zarar vermemek kaydıyla),
- Gerektiğinde **açık rıza** (m.5/1): yalnızca zorunlu olmayan işlemler için ayrıca alınır.

## 5. Aktarım
- Kişisel veriler, hizmetin sunulduğu **Türkiye'deki** altyapıda işlenir ve saklanır.
- **Yurt dışına aktarım yapılmaz** (KVKK m.9). Tarama, self-host edilen yente örneği ile
  yapılır; veri dış tarama API'lerine gönderilmez. Faz 1'de LLM/dış AI çağrısı yoktur.
- Yurt içinde, yalnızca hizmetin ifası için zorunlu barındırma/altyapı sağlayıcılarına,
  veri işleyen sıfatıyla ve sözleşmesel gizlilik güvenceleriyle aktarım olabilir
  ({{BARINDIRMA_SAGLAYICI}}).

## 6. Saklama Süresi
- Hesap ve işlem verileri, ilişki süresince ve mevzuatın gerektirdiği süre boyunca
  (asgari {{SAKLAMA_YILI}} yıl) saklanır; süre sonunda silinir/yok edilir/anonimleştirilir.
- Denetim kayıtları, değiştirilemez (append-only) biçimde ve tamper-evident hash zinciri
  ile tutulur.

## 7. İlgili Kişinin Hakları (KVKK m.11)
İlgili kişi; verilerinin işlenip işlenmediğini öğrenme, bilgi talep etme, amaca uygun
kullanılıp kullanılmadığını öğrenme, düzeltme/silme/yok etme, işlemenin sınırlandırılması,
otomatik sistemlerle aleyhe sonuç çıkmasına itiraz ve zararın giderilmesini talep etme
haklarına sahiptir.

**Başvuru:** Talepler {{BASVURU_KANALI}} (ör. {{E_POSTA}} / {{KEP_ADRESI}}) üzerinden
iletilebilir; Veri Sorumlusuna Başvuru Usul ve Esasları Hakkında Tebliğ uyarınca en geç
**30 gün** içinde yanıtlanır.

**Yürürlük tarihi:** {{TARIH}} · **Sürüm:** v1 (taslak)
