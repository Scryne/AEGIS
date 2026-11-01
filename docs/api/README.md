# AEGIS API — hızlı başlangıç

AEGIS'in bütün ekranları aynı REST API'yi kullanır; bu belge, kendi sisteminizi (ERP, müşteri
kabul akışı, ödeme altyapısı) AEGIS'e bağlamak için gereken her şeyi içerir. Tam şema:
[`docs/openapi.json`](../openapi.json) (OpenAPI 3.1), Postman koleksiyonu:
[`aegis.postman_collection.json`](aegis.postman_collection.json).

- **Taban adres:** `https://<kurumunuzun-adresi>/api/v1`
- **Biçim:** JSON (UTF-8). Zamanlar ISO 8601, UTC.
- **Sürüm:** `/v1` dondurulmuştur: alan ekleme ve yeni uç geriye uyumludur; alan kaldırma, tip ya
  da anlam değişikliği yalnız `/v2` ile gelir ve `/v1` en az 12 ay birlikte yaşar.

## 1. Kimlik doğrulama: API anahtarı

Anahtarı kurum **sahibi** açar: *Entegrasyonlar → API anahtarları → Yeni anahtar*. Tam anahtar
yalnız o an bir kez gösterilir; AEGIS yalnız özetini saklar. Kaybederseniz iptal edip yenisini açın.

| Anahtar rolü | Ne yapabilir |
|---|---|
| `analyst` | Varlık açar, tarama ve toplu tarama başlatır, her şeyi okur |
| `auditor` | Yalnız okur |

Eşleşme onayı, vaka kararı ve anahtar/webhook yönetimi bilinçli olarak anahtara verilmez: bunlar
insan kararıdır ve kişinin oturumuyla yapılır.

```bash
curl https://aegis.example.com/api/v1/entities \
  -H "X-API-Key: aeg_xxxxxxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

`Authorization: Bearer aeg_…` biçimi de kabul edilir. Anahtar başına dakikada 120 istek sınırı
vardır; aşılırsa `429` ve `Retry-After` başlığı döner.

## 2. İlk tarama

```bash
# 1) Müşteriyi kütüğe ekleyin (aynı vergi no varsa yeni kayıt açmadan önce kontrol edin)
curl -X POST https://aegis.example.com/api/v1/entities \
  -H "X-API-Key: $AEGIS_KEY" -H "Content-Type: application/json" \
  -d '{"name": "Örnek Lojistik A.Ş.", "schema_type": "Company", "tax_number": "1234567890"}'

# 2) Kütükteki kaydı (yöneticileri ve gerçek faydalanıcılarıyla) tarayın
curl -X POST https://aegis.example.com/api/v1/screenings/from-entity/<entity_id> \
  -H "X-API-Key: $AEGIS_KEY"
```

Yanıttaki `summary` alanı karar dağılımını verir: `flagged` (yüksek skorlu aday),
`sanction_hits`, `pep_hits`, `pending` (insan kararı bekleyen). **Yüksek skor eşleşme demek
değildir**: AEGIS hiçbir adayı kendiliğinden onaylamaz; karar uyum uzmanınızındır. Tarama motoruna
ulaşılamazsa yanıt `502` ve `status: "failed"` olur; başarısız tarama hiçbir zaman "temiz"
sayılmaz.

Her tarama aylık sorgu hakkınızdan özne sayısı kadar düşer. Hak dolduysa ve planınız aşıma izin
vermiyorsa `402 quota_exceeded` döner; kısmi tarama yapılmaz.

## 3. Toplu tarama

```bash
# Önizleme (dosya saklanmaz): başlıklar, önerilen sütun eşlemesi, ilk 20 satırın doğrulaması
curl -X POST https://aegis.example.com/api/v1/batches/preview \
  -H "X-API-Key: $AEGIS_KEY" -F file=@musteriler.csv

# Kaydet + başlat
curl -X POST https://aegis.example.com/api/v1/batches \
  -H "X-API-Key: $AEGIS_KEY" -F file=@musteriler.csv \
  -F 'mapping={"name":"Ticaret Unvanı","tax_number":"VKN","schema_type":"Tür"}'
curl -X POST https://aegis.example.com/api/v1/batches/<batch_id>/start -H "X-API-Key: $AEGIS_KEY"

# Sonuç (riske göre sıralı) ya da Excel'e hazır CSV
curl "https://aegis.example.com/api/v1/batches/<batch_id>/rows?sort=risk&hits=true" -H "X-API-Key: $AEGIS_KEY"
curl -o sonuc.csv https://aegis.example.com/api/v1/batches/<batch_id>/export.csv -H "X-API-Key: $AEGIS_KEY"
```

En çok 1.000 satır. TCKN sütunu kabul edilmez (kütükte şifreli saklanır; kişileri kimlik
numarasıyla tek tek ekleyin). Kütükte birden çok benzer kayıt varsa satır taranmaz,
`needs_review` olur ve karar ekranda verilir. Toplu iş bitince `batch.completed` olayı gelir.

## 4. Webhook'lar

*Entegrasyonlar → Webhook'lar*'dan bir `https` adresi ve olayları seçin. İmza sırrı (`whsec_…`)
yalnız o an gösterilir.

| Olay | Ne zaman | `data` |
|---|---|---|
| `screening.completed` | Tarama bitti (başarılı ya da başarısız) | `screening_id`, `entity_id`, `status`, sayılar |
| `alert.raised` | İzlenen varlıkta önemli fark | `alert_id`, `entity_id`, `severity`, `kinds`, `case_id` |
| `case.updated` | Vaka açıldı, durumu değişti ya da atandı | `case_id`, `entity_id`, `status`, `severity`, `edd`, `change` |
| `batch.completed` | Toplu iş bitti | `batch_id`, satır sayıları, riskli satır sayıları |
| `ping` | Ekrandaki "Test gönder" | `endpoint_id` |

Gövde örneği:

```json
{"id": "3f6c…", "type": "alert.raised", "created_at": "2026-11-01T02:45:12+00:00",
 "data": {"alert_id": "…", "entity_id": "…", "severity": "critical", "kinds": ["new_match"], "case_id": "…"}}
```

Yük **kişisel veri taşımaz**: yalnız kimlikler ve durumlar. Ayrıntıyı API'den kimlikle çekin
(`GET /screenings/{id}`, `GET /cases/{id}` …). Böylece veri, yalnız sizin kimliği doğrulanmış
çağrınızla ortamımızdan çıkar.

### İmzayı doğrulayın

Her istek `X-Aegis-Signature: t=<unix>,v1=<hex>` taşır. `v1 = HMAC-SHA256(sır, "<t>.<ham gövde>")`.
Ham gövdeyi (ayrıştırmadan önceki baytları) kullanın, zamanı ±5 dakikayla sınırlayın ve sabit
zamanlı karşılaştırın:

```python
import hashlib, hmac, time

def dogrula(sir: str, govde: bytes, baslik: str, tolerans: int = 300) -> bool:
    parcalar = dict(p.split("=", 1) for p in baslik.split(","))
    t = int(parcalar["t"])
    if abs(time.time() - t) > tolerans:
        return False
    beklenen = hmac.new(sir.encode(), f"{t}.".encode() + govde, hashlib.sha256).hexdigest()
    return hmac.compare_digest(beklenen, parcalar.get("v1", ""))
```

```javascript
import crypto from "node:crypto";

export function dogrula(sir, govde /* Buffer */, baslik, tolerans = 300) {
  const p = Object.fromEntries(baslik.split(",").map((s) => s.split("=", 2)));
  const t = Number(p.t);
  if (Math.abs(Date.now() / 1000 - t) > tolerans) return false;
  const beklenen = crypto.createHmac("sha256", sir).update(`${t}.`).update(govde).digest("hex");
  const a = Buffer.from(beklenen), b = Buffer.from(p.v1 ?? "");
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}
```

### Teslim ve yeniden deneme

2xx dışındaki her yanıt (ya da 10 sn'de cevap gelmemesi) başarısızlıktır. Yeniden deneme:
30 sn, 2 dk, 10 dk, 1 sa, 6 sa; altıncı başarısızlıktan sonra teslim `dead` olur ve ekrandan
yeniden gönderilebilir. Aynı olay birden çok kez gelebilir: `id` alanıyla tekilleştirin.
`X-Aegis-Delivery` her denemenin kimliğidir. Yönlendirme (3xx) izlenmez. Webhook adresi iç ağa
ya da ayrılmış bir adrese çözümlenirse teslim yapılmaz (adres her denemede yeniden denetlenir).

## 5. Hatalar

```json
{"error": {"code": "quota_exceeded", "message": "…", "details": [{"used": 300, "included": 300}]}}
```

| HTTP | `code` | Anlamı |
|---|---|---|
| 400 | `validation_error` | Girdi geçersiz (mesaj Türkçe ve düzeltme yolunu söyler) |
| 401 | `unauthorized` | Anahtar yok, geçersiz, iptal edilmiş ya da süresi dolmuş |
| 402 | `quota_exceeded` | Aylık sorgu hakkı doldu |
| 403 | `forbidden` | Anahtarın rolü bu işe yetmiyor |
| 404 | `not_found` | Kayıt yok ya da başka kuruma ait (ikisi ayırt edilmez) |
| 409 | `conflict` / `plan_limit` | Durum uygun değil (ör. kapanmış vaka) ya da plan sınırı |
| 429 | `rate_limited` | Dakikalık istek sınırı; `Retry-After` kadar bekleyin |
| 502 | — | Tarama motoruna ulaşılamadı; tarama `failed` olarak kaydedildi |
