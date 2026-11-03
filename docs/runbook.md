# AEGIS işletim el kitabı

Her arıza için: **belirti** (kullanıcı ne görür), **tespit** (hangi sinyal), **kurtarma** (sırayla
ne yapılır). Ürün davranışı hep aynı ilkeye dayanır: **yapılamayan iş "temiz" sayılmaz**; tarama
`failed` kalır, izleme alarm üretmez ama günlüğe düşer, webhook `dead` olur. Hiçbir arıza sessizce
"risk yok" sonucuna dönüşmez.

Komutlar Docker Compose kurulumuna göredir. Üretimde `docker compose` yerine
`docker compose -p aegis -f infra/compose/docker-compose.prod.yml --env-file /etc/aegis/aegis.env`
kullanılır; kurulum, dağıtım, yedek ve geri yükleme `docs/deploy.md`'de.

## 1. Yaptırım veri kümesi senkronu başarısız / bayat

- **Belirti:** Tarama sayfasında "yaptırım verisi bayat" uyarısı; yeni listelenen kişi bulunmuyor.
- **Tespit:** `sanctions.sync` görevinin günlüğünde `yaptirim_verisi_bayat` (hata düzeyi, Sentry'ye
  düşer); `GET /api/v1/screenings/datasets` yanıtında `any_stale: true`. Eşik
  `SANCTIONS_STALENESS_HOURS` (24).
- **Kurtarma:**
  1. yente ayakta mı: `curl -s $YENTE_URL/healthz`.
  2. Senkronu elle tetikle: `docker compose exec worker celery -A aegis_worker.celery_app call sanctions.sync`.
  3. OpenSanctions erişilemiyorsa bekle; bu sürede yapılan taramaların raporunda veri kümesi sürümü
     donuk olarak yazılıdır (denetimde "hangi veriyle tarandı" cevabı hazır).
  4. MASAK listesi kaynağı (`MASAK_SOURCE_PATH`) eksikse yalnız o adım atlanır, iş düşmez.

## 2. Elasticsearch / yente kesintisi

- **Belirti:** Tarama uçları `502`, tarama `failed` ("tarama motoruna ulaşılamadı"); toplu iş
  satırları "yeniden denenebilir"; gece izlemesi o varlıklar için alarm üretmez.
- **Tespit:** API günlüğünde `screening_tamamlandi status=failed`; izleme özetinde `failed > 0`.
- **Kurtarma:**
  1. `docker compose logs --tail 200 elasticsearch yente`; disk doluluğu (`df -h`) ilk şüphe.
  2. ES yeniden başlat: `docker compose restart elasticsearch && docker compose restart yente`.
  3. İndeks bozuksa sıfırdan kur: `docker compose stop yente && docker compose exec elasticsearch
     curl -XDELETE localhost:9200/yente-*` ardından `docker compose start yente` (yente açılışta
     indeksler; 2026 veri kümesiyle ~20–40 dk). Bu sürede taramalar `failed` döner, veri kaybı yok.
  4. Toplu işler: ekranda "Başarısızları yeniden dene" (en çok 3 deneme). Başarısız taramalar kota
     tüketmez (ADR-0018).
  5. İzleme: ertesi gece koşusu aynı farkı yeniden bulur; beklemek istemezsen İzleme → elle koşu.

## 3. Kuyruk birikmesi (Celery / Redis)

- **Belirti:** Toplu iş "Sırada" kalıyor; derin tarama sonuçlanmıyor; webhook teslimleri gecikiyor.
- **Tespit:** `docker compose exec redis redis-cli llen aegis` (bekleyen iş); worker günlüğünde
  hata yok ama iş akmıyorsa worker düşmüştür.
- **Kurtarma:**
  1. `docker compose ps worker beat`; düşükse `docker compose up -d worker beat`.
  2. Toplu iş kaybolmaz (`queued`/`running` satırlar veritabanında); worker dönünce kaldığı yerden
     devam eder. Acilse sahip/uyum uzmanı ekrandan "Şimdi işle".
  3. Redis verisi silindiyse yalnız kuyruk mesajları gider: toplu işleri ekrandan yeniden başlatmak
     gerekmez, "Şimdi işle" ya da `celery call batch.process --kwargs '{"tenant_id": "…", "batch_id": "…"}'`.
  4. Oran sınırı sayaçları Redis'tedir; Redis yokken sınırlar uygulanmaz (fail-open, ADR-0016).

## 4. Webhook teslimi başarısız (müşteri tarafı)

- **Belirti:** Müşteri olay almadığını söyler.
- **Tespit:** Entegrasyonlar → uç → teslim kaydı: `last_status_code` / `last_error`; `dead` teslimler.
- **Kurtarma:**
  1. Hata 4xx ise müşteri imzayı yanlış doğruluyordur (ham gövde, ±5 dk saat farkı) → `docs/api`.
  2. "iç ağa ya da ayrılmış bir adrese çıkamaz" ise müşterinin adresi özel IP'ye çözümleniyor;
     herkese açık bir adres vermesi gerekir (güvenlik, ADR-0016).
  3. Sorun giderilince `dead` teslimleri "Yeniden gönder". Olaylar `id` ile tekilleştirilmelidir.

## 5. Ödeme / faturalama webhook'u

- Henüz ödeme sağlayıcısı yok (ADR-0018: ticari karar açık). Sağlayıcı seçilince bu bölüm, sağlayıcının
  imzalı bildirimi düşerse ne olacağıyla doldurulur. O zamana kadar dönem dökümü (`usage_statement`)
  her gün 03:15 UTC'de önceki ayı dondurur; kaçırılan koşu ertesi gün telafi edilir.

## 6. Denetim izi zinciri kırık

- **Belirti:** Denetim İzi sayfasında "zincir doğrulanamadı".
- **Tespit:** `GET /api/v1/audit/verify` → `broken_seq`.
- **Kurtarma:** Bu bir güvenlik olayıdır, onarılmaz: kırık halkadan itibaren veritabanı erişim
  günlükleri incelenir, en son doğrulanmış yedekle karşılaştırılır, müşteriye ve gerekiyorsa KVKK
  süreçlerine göre bildirim yapılır. Tetikleyici ve REVOKE'un yerinde olduğunu kontrol et (ADR-0004).

## 7. Şifre çözme hatası (`DecryptionError`)

- **Belirti:** Varlık listesi ya da ŞİB taslağı 500.
- **Tespit:** API günlüğünde `Şifre çözme başarısız (yanlış anahtar veya kurcalanmış veri)`.
- **Kurtarma:** `FIELD_ENCRYPTION_KEY` dağıtımda değişmiş demektir. Önceki anahtarı geri koy; anahtar
  döndürme (yeniden şifreleme) ayrı, planlı bir iştir. Ürün bilinçli olarak kapalı başarısız olur:
  çözülemeyen kayıt "boş" gösterilmez.

## 8. Saklama süresi

- `retention.dispose` her gün **kuru çalışır**: süresi geçmiş adayları tablo başına sayar ve
  `retention.dry_run` denetim olayı yazar; hiçbir şey silmez. Gerçek silme ayrı bir kararla açılır
  (ilişki bitişi, nesne deposu sırası, yasal saklama istisnaları). Rapor Denetim İzi'nden okunur.

## 9. Veri kaybı / yedekten dönüş

- **Belirti:** veritabanı hacmi bozuk ya da yanlışlıkla silinmiş; sunucu kaybı.
- **Tespit:** `saglik.sh` uyarısı (servis düşük, `/readyz` hazır değil); Postgres günlüğünde bozulma.
- **Kurtarma:** `docs/deploy.md` → "Geri yükleme": `geri_yukle.sh liste` → `indir` → önce
  `tatbikat` (zincir doğrulaması geçmeli) → `uretim --onayla --nesneler`. Aynı
  `FIELD_ENCRYPTION_KEY` şart (§7). Son yedekten sonraki işlemler kaybolur; müşteriye ve
  gerekiyorsa KVKK sürecine göre bildirim yapılır.

## 10. Uyarı geldi (saglik.sh)

- Uyarı metni hangi kontrolün düştüğünü söyler. Yedek uyarısı: `/var/log/aegis-yedek.log`.
  TLS uyarısı: `docker compose … logs caddy` (DNS kaydı, 80/443 erişimi, ACME sınırı). Disk:
  önce `docker system df`, sonra ES indeks boyutu.

## Ölçümler (2026-11-01, yerel)

- 1.000 satırlık toplu iş (taklit yente, gecikmesiz): 20,8 sn, saniyede 48 satır; tüm satırlar
  sonuçlandı (855 tarandı, 145 ER belirsiz → insana); kota sayacı taranan satırla aynı (855).
  Gerçek yente gecikmesiyle süre satır × motor yanıtı kadar uzar (işleme satır satır).
  `scripts/load_batch_1k.py`.
