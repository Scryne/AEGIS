# ADR-0016: Genel API — rol kapsamlı API anahtarı, giden kutulu imzalı webhook

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-01
- **İlgili:** ROADMAP E3.4, Phase 3 çıkış ölçütü 2; ADR-0002 (RLS ve kimlik denetim düzlemi
  istisnası), ADR-0005 (alan şifreleme), Invariant 3 (veri yerelliği)

## Kararlar

### 1. Anahtar rolle kapsamlanır; karar veren roller anahtara verilmez
Anahtar `analyst` (varlık, tarama, toplu tarama, okuma) ya da `auditor` (okuma) rolüyle açılır ve
mevcut `require_role` denetiminden geçer; uç başına ayrı bir "kapsam" listesi tutulmaz (aynı kuralı
iki yerde tutmak kayma üretir). Sahip ve uyum uzmanı rolleri anahtara verilmez: eşleşme onayı, vaka
kararı ve anahtar/webhook yönetimi insan oturumu ister. Entegrasyon uçları ayrıca anahtarla gelen
her isteği reddeder (rolü yetse bile).

### 2. Saklama: yalnız özet; `api_key` kimlik denetim düzlemi
Biçim `aeg_<önek12>_<gizli40>`; önek düz, tam anahtarın SHA-256 özeti saklanır (yüksek entropili
rastgele değer olduğu için yavaş parola özeti gereksiz), karşılaştırma sabit zamanlı. İstek
geldiğinde kiracı bağlamı yoktur, anahtar önekle aranır: tablo `organization`/`membership` gibi
RLS'siz kimlik denetim düzlemidir ve her uç `principal.tenant_id` ile açıkça süzer. Kiracılar arası
erişim (listeleme, iptal) uç testleriyle kapanır.

### 3. Oran sınırı ve ölçüm
Anahtar başına dakikada 120 istek (Redis, mevcut sınırlayıcı; Redis yoksa fail-open, giriş
uçlarıyla aynı karar). Anahtarla yapılan taramalar `requested_by_user_id = anahtar` ile mevcut kota
sayacına girer; ayrı bir ölçüm hattı E3.5'e kalır.

### 4. Webhook: giden kutusu + worker teslimi
Olay, işi yazan transaction'da `webhook_delivery` satırı olarak yazılır (iş geri alınırsa olay da
yok, commit edilirse kaybolmaz); ağ çağrısı iş isteğinde hiç yapılmaz. Worker her 30 sn zamanı
gelen teslimleri `FOR UPDATE SKIP LOCKED` ile dener. Yeniden deneme 30 sn, 2 dk, 10 dk, 1 sa, 6 sa;
sonra `dead`, elle yeniden gönderilebilir. Olaylar: `screening.completed` (`_finalize`, senkron ve
derin tarama ortak noktası), `alert.raised`, `case.updated` (açılış, durum, atama), `batch.completed`.

### 5. İmza ve yük
`X-Aegis-Signature: t=<unix>,v1=HMAC-SHA256(sır, "<t>.<gövde>")`; alıcı ±5 dk ile doğrular. Sır
şifreli saklanır, yalnız oluşturma/yenileme yanıtında görünür. Yük kişisel veri taşımaz (kimlik ve
durumlar); ayrıntı kimlikle API'den çekilir: veri ortamdan yalnız müşterinin kimliği doğrulanmış
çağrısıyla çıkar (Invariant 3 ile uyumlu).

### 6. SSRF
Hedef yalnız `https`, kimlik bilgisi içermez; çözümlenen **her** adres herkese açık olmalıdır
(loopback, özel, bağlantı yerel — bulut üst veri adresi dahil —, ayrılmış, çok noktaya yayın
reddedilir). Denetim kayıtta ve her teslimde yapılır; yönlendirme izlenmez. Kalan risk: denetim ile
bağlantı arasında DNS'in değişmesi (rebinding). Kapatmak için çözülen adrese sabitlenmiş bağlantı
gerekir; E3.7 güvenlik geçişine not edildi. Geliştirme ve test için `WEBHOOK_ALLOW_HTTP` /
`WEBHOOK_ALLOW_PRIVATE` ayarları vardır, üretimde kapalıdır.

### 7. Sürüm ve belge
`/v1` donduruldu: ekleme geriye uyumlu, kaldırma/anlam değişikliği yalnız `/v2` ile ve `/v1` en az
12 ay birlikte yaşar (ürün varsayılanı; ticari sözleşmede değiştirilebilir). Belge
`docs/api/README.md`, Postman koleksiyonu `scripts/export_postman.py` ile şemadan üretilir.

## Doğrulama

Birim 12 (anahtar biçimi, imza/tolerans/kurcalama, takvim, SSRF 7 adres + karışık çözümleme),
entegrasyon 4 (anahtar yaşam döngüsü ve kapsamı, oran sınırı, imzalı teslim + yeniden deneme +
sır yenileme + abone olunmayan olay + kiracı izolasyonu, üretim modunda iç adres reddi). 8 koruma
tek tek kaldırıldığında testler düştü (ilk turda kaçan ikisi için test eklendi).
