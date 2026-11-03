# AEGIS üretim kurulumu, dağıtım, yedek ve geri yükleme (E1.6)

Tek sunucu, Docker Compose (R6). Arıza anında ne yapılacağı `docs/runbook.md`'de; bu belge
kurulumu, günlük işletimi ve geri yüklemeyi anlatır.

> **Durum (2026-11-03):** dosyalar yazıldı ve yerelde sınandı (aşağıda "Ne doğrulandı").
> Gerçek bir sunucuda hiç çalıştırılmadı: sunucu seçimi, alan adı, TLS sertifikası, uzak
> yedek hedefi ve telefon bildirimi **henüz yok**.

## Dosyalar

| Dosya | Ne |
|---|---|
| `infra/compose/docker-compose.prod.yml` | 11 servis: caddy, web, api, migrate, worker, beat, postgres, redis, minio, elasticsearch, yente |
| `infra/compose/aegis.env.example` | Ortam dosyası şablonu (değer yok) → sunucuda `/etc/aegis/aegis.env` |
| `infra/compose/initdb-prod/10-app-role.sh` | RLS'ye tabi `aegis_app` rolü, parolası ortamdan |
| `infra/caddy/Caddyfile` | Otomatik TLS, HTTP→HTTPS, güvenlik başlıkları |
| `infra/ops/deploy.sh` | Tek komutluk dağıtım + `--geri-al` |
| `infra/ops/yedek.sh` | Gece yedeği: Postgres + nesne deposu → şifreli ikinci konum |
| `infra/ops/geri_yukle.sh` | `liste` · `indir` · `tatbikat` · `uretim` |
| `infra/ops/saglik.sh` | 5 dakikalık sağlık kontrolü + uyarı |
| `infra/ops/aegis.cron` | Yedek ve sağlık kontrolü zamanlaması |
| `.github/workflows/deploy.yml` | Yalnız elle tetiklenen derle → it → SSH ile dağıt |
| `scripts/kiraci_ac.py` | Kiracı + sahip + davet |
| `scripts/denetim_zinciri_dogrula.py` | Her kiracının denetim izi zinciri (geri yükleme sonrası) |

## Mimari

```
internet ──443──► caddy ──► web:3000 ──(/api/v1 vekili, httpOnly çerez)──► api:8000
                     └────► api:8000  (api.<alan>: X-API-Key ile genel API)
api, worker, beat ──► postgres (aegis_app, RLS) · redis · minio · yente ──► elasticsearch
migrate (tek seferlik) ──► postgres (aegis, ayrıcalıklı)
```

- Dışarı yalnız 80/443 açık. Postgres, Redis, ES, yente, MinIO, API hiçbir portu sunucuya bağlamaz.
- Her serviste bellek/CPU sınırı, `restart: unless-stopped`, sağlık kontrolü, döngüsel günlük.
  Toplam bellek sınırı ≈ 15 GB: **en az 16 GB RAM, 4 vCPU, 100 GB SSD**.
- Sırlar yalnız ortam dosyasından gelir; compose'da her sır `${AD:?}`: eksikse hiçbir şey başlamaz.
- Beat ayrı servis (worker'dan `-B` kalktı): worker çoğaltılırsa zamanlanmış işler iki kez koşmaz.

## İlk kurulum (sunucuda bir kez)

Seçim ölçütü (KVKK, Invariant 3): Türkiye'de veri merkezi olan bir sağlayıcı. Bu karar Scryne'da.

1. Ubuntu LTS, Docker Engine + compose eklentisi, `curl`, `openssl`. Güvenlik duvarı: yalnız 22, 80, 443.
   Disk şifrelemesi (E1.2 ertelenen kalem) sağlayıcının şifreli blok depolamasıyla ya da LUKS ile.
2. Dağıtım kullanıcısı: `adduser deploy && usermod -aG docker deploy`; yalnız anahtarla SSH.
3. Depo: `sudo git clone https://github.com/Scryne/AEGIS /opt/aegis && sudo chown -R deploy /opt/aegis`.
   Özel depo için salt-okunur bir deploy key.
4. GHCR'dan çekme (özel paket): `docker login ghcr.io` — yalnız `read:packages` yetkili jetonla.
5. Ortam dosyası:
   ```bash
   sudo install -d -m 700 /etc/aegis
   sudo install -m 600 /opt/aegis/infra/compose/aegis.env.example /etc/aegis/aegis.env
   ```
   Doldurun. Parolaları `openssl rand -hex 32` ile üretin (URL'e girdikleri için yalnız hex).
   `FIELD_ENCRYPTION_KEY`: `uv run python -c "from aegis_core.security.encryption import generate_key; print(generate_key())"`.
   **Bu dosyanın ve özellikle `FIELD_ENCRYPTION_KEY` ile `BACKUP_CRYPT_*`'ın bir kopyası sunucudan
   ayrı, çevrimdışı bir parola kasasında durmalı.** Anahtar kaybı = şifreli TCKN'ler ve uzak
   yedekler geri gelmez.
6. MinIO imajı: Docker Hub'daki `minio/minio` 2026-11-03 itibarıyla 404 dönüyor. Varsayılan
   `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` **doğrulanmadı** — önce
   `docker pull` ile deneyin; çekilemiyorsa erişilebilir bir S3-uyumlu imajı `AEGIS_MINIO_IMAGE`'a
   yazın (sağlık kontrolü `mc ready local` kullanır; başka imajda o satır uyarlanmalı).
7. DNS: `AEGIS_DOMAIN` ve `AEGIS_API_DOMAIN` için A/AAAA kayıtları sunucuya. Caddy ilk istekte
   sertifikayı alır; 80 ve 443 dışarıdan açık olmalı.
8. İlk dağıtım: GitHub'da "Deploy (üretim)" iş akışını çalıştırın ya da sunucuda
   `infra/ops/deploy.sh <commit-sha>` (imajlar GHCR'da olmalı).
9. Zamanlanmış işler: `sudo cp /opt/aegis/infra/ops/aegis.cron /etc/cron.d/aegis`.
10. Dış izleme: sunucu tümden düşerse `saglik.sh` de çalışmaz. Sunucu dışından bir uptime
    izleyicisi `https://<api-alanı>/readyz` adresini yoklamalı ve telefona bildirmeli.
11. İlk yedek + geri yükleme tatbikatı (aşağıda) — pilotlardan önce zorunlu.
12. İlk kiracı: aşağıdaki "Kiracı açma".

## Dağıtım

**GitHub'dan (önerilen):** Actions → "Deploy (üretim)" → Run workflow → `DAGIT` yazın. İş, commit
SHA'sıyla üç imajı GHCR'a iter, SSH ile bağlanıp sunucuda depoyu o SHA'ya alır ve
`infra/ops/deploy.sh <sha>` çalıştırır. push/PR ile asla tetiklenmez.

GitHub'da tanımlanacaklar (Settings → Environments → `production`; zorunlu onaylayıcı önerilir):

| Ad | Tür | İçerik |
|---|---|---|
| `DEPLOY_HOST` | secret | sunucu adı / IP |
| `DEPLOY_USER` | secret | `deploy` |
| `DEPLOY_SSH_KEY` | secret | yalnız bu iş için üretilmiş ed25519 özel anahtar |
| `DEPLOY_KNOWN_HOSTS` | secret | `ssh-keyscan -t ed25519 <host>` çıktısı |
| `DEPLOY_PATH` | variable | depo yolu (varsayılan `/opt/aegis`) |

**Sunucudan:** `infra/ops/deploy.sh <etiket>`. Sıra: compose doğrulama → imaj çekme → Postgres
→ `migrate` (ayrıcalıklı rol, tek seferlik) → tüm servisler → hepsi sağlıklı olana dek bekleme
(varsayılan 600 sn) → etiketi `/var/lib/aegis/deployed-tag`'e yazma → dışarıdan `/readyz`.
Sağlık beklemesi dolarsa etiket yazılmaz, çıkış 1.

**Geri alma:** `infra/ops/deploy.sh --geri-al` önceki etikete döner. Migration'lar ileri
yönlüdür; geri alma şemayı geri almaz. Şema değiştiren bir sürümü geri almak gerekiyorsa
önce o sürümden hemen önceki yedeğe dönmek (aşağıda "uretim") gerekebilir.

## Kiracı açma

```bash
docker compose -p aegis -f infra/compose/docker-compose.prod.yml --env-file /etc/aegis/aegis.env \
  run --rm api python scripts/kiraci_ac.py \
  --ad "Örnek Mali Müşavirlik" --slug ornek-ofis --sahip-eposta sahip@ornek.com.tr --plan pilot
```

- Kurum, parolasız sahip hesabı ve üyelik tek transaction'da açılır; aynı transaction'da kurumun
  denetim izinin ilk halkası `tenant.provision` yazılır. Sahibe 72 saatlik (en çok 7 gün)
  parola belirleme bağlantısı gider; davet ayrı `tenant.invite` olayıdır. E-posta olaya yazılmaz.
- Uygulama rolüyle (RLS'ye tabi) çalışır; ayrıcalıklı bağlantı gerekmez.
- SMTP yoksa araç hiçbir şey açmadan durur; bağlantıyı elle iletmek için `--baglantiyi-yazdir`.
- Süresi geçen davet: `--yeniden-davet --slug ornek-ofis`. Plan değişikliği: `scripts/plan_ata.py`.

## Yedek

`infra/ops/yedek.sh` her gece 01:30 UTC:

1. `pg_dump` (özel biçim) → `/var/backups/aegis/postgres/aegis-<zaman>.dump` + `.sha256`.
2. Döküm `pg_restore --list` ile okunabilirliği denetlenir; bozuksa iş düşer.
3. İkinci konum: döküm ve belge deposu (`aegis-documents`) rclone ile S3-uyumlu başka bir
   sağlayıcı/bölgeye, **istemci tarafında şifrelenerek** (`crypt`). Belgeler `copy` ile gider —
   kaynakta silinen belge uzakta kalır; saklama süresi imhası gerçek silmeye geçtiğinde (E3.7)
   uzak kopya için de karar verilmeli.
4. `.son-yerel` / `.son-uzak` işaretleri; `saglik.sh` 26 saatten eskiyse uyarır.
5. Yerelde 14, uzakta 35 günden eski dökümler silinir.

Kapsam dışı (bilerek): ES indeksi (yente yeniden kurar), MASAK FtM dosyası (günlük iş üretir),
Redis (işler veritabanında), Caddy sertifikaları, ortam dosyası (parola kasasında).

**Uzak hedef seçimi (açık, Scryne):** KVKK yurt dışı aktarım kuralı uzak yedeğin de Türkiye'de
olmasını gerektirebilir; içerik istemci tarafında şifreli olsa da karar hukuki incelemeyle.

## Geri yükleme

```bash
infra/ops/geri_yukle.sh liste                                    # yerel + uzak dökümler
infra/ops/geri_yukle.sh indir aegis-20261103T013000Z.dump        # uzaktan indir (şifre çözülür)
infra/ops/geri_yukle.sh tatbikat /var/backups/aegis/postgres/aegis-….dump
infra/ops/geri_yukle.sh uretim  /var/backups/aegis/indirilen/aegis-….dump --onayla --nesneler
```

- **tatbikat** canlı veritabanına dokunmaz: dökümü `aegis_tatbikat`a yükler, SHA-256'yı denetler,
  tablo sayılarını ve şema sürümünü basar, **her kiracının denetim izi hash zincirini doğrular**
  (`scripts/denetim_zinciri_dogrula.py`; kırık halka = çıkış 1), sonra tatbikat veritabanını siler.
- **uretim** önce caddy/web/api/worker/beat'i durdurur, `aegis`'i dökümle tek transaction'da
  değiştirir, `migrate` koşar, zinciri doğrular, `--nesneler` ile belgeleri uzaktan geri kopyalar
  (var olanın üzerine yazmaz), servisleri açar. Ardından `saglik.sh`.
- Geri yüklenen veritabanı **aynı `FIELD_ENCRYPTION_KEY`** ister; farklı anahtarla TCKN alanları
  çözülemez (runbook §7).

### Tatbikat kaydı

| Tarih | Ortam | Döküm | Süre | Zincir | Not |
|---|---|---|---|---|---|
| 2026-11-03 | yerel (Docker, `postgres:16`, uzak kopya yok) | 2 kiracı, 5 olay, 140 KB | 1 sn | 2/2 sağlam | Kasıtlı kurcalama (trigger kapatılıp bir olay değiştirildi) `row_hash_mismatch` ile yakalandı. Uzak kopya ve gerçek sunucu tatbikatı **yapılmadı**. |

Yol haritasının istediği "pilotlardan önce bir kez" tatbikat **gerçek sunucuda, uzak kopyadan
indirilen dökümle** yapılmalı ve bu tabloya yazılmalı.

## Sağlık kontrolü ve uyarı

`infra/ops/saglik.sh` 5 dakikada bir: arayüz ve API dışarıdan TLS ile yanıt veriyor mu, `/readyz`
(DB + Redis zorunlu; yente düşükse ayrı uyarı), sertifika bitişine 14 günden az mı, sağlıksız/durmuş
servis var mı, yedekler 26 saatten eski mi, disk %85'ten dolu mu. Sorun olursa
`ALERT_WEBHOOK_URL`'e düz metin POST (ör. kendi ntfy konunuz → telefon); aynı sorun sürerken en çok
saatte bir, düzelince "düzeldi". Sunucunun tümden düşmesi için dış izleyici gerekir (kurulum 10).

## Ne doğrulandı, ne doğrulanmadı (2026-11-03)

Doğrulandı (bu depoda, yerelde):
- `docker compose config`: üretim dosyası sahte değerlerle çözümleniyor; tek bir sır eksikken
  başlamıyor (`required variable AUTH_SECRET is missing a value`).
- `initdb-prod`: `aegis_app` süper kullanıcı olmadan, ortamdaki parolayla oluşuyor.
- Kiracı açma CLI'ı: entegrasyon testi (`apps/api/tests/integration/test_provisioning.py`) +
  yerel Postgres konteynerinde iki kiracı.
- `yedek.sh --yalniz-yerel` + `geri_yukle.sh tatbikat`: döküm, SHA-256, ayrı veritabanına geri
  yükleme, tablo sayıları; zincir doğrulaması ana makineden aynı betikle (api imajı bu ortamda
  derlenemedi).
- shellcheck, actionlint temiz; üretim dosyası değişmezleri `infra/tests/test_uretim_dosyalari.py`.

Doğrulanmadı:
- Gerçek sunucu, alan adı, TLS sertifikası alımı, Caddy'nin kendisi (bu ortamdan Docker Hub 429;
  Caddyfile CI'da `caddy validate` ile denetlenir).
- İmajların GHCR'a itilmesi ve deploy iş akışının uçtan uca koşusu (bilerek tetiklenmedi).
- rclone ile uzak kopya ve uzaktan indirip geri yükleme; MinIO imaj etiketi.
- Telefon bildirimi ve dış uptime izleyicisi.
- Bellek sınırlarının gerçek yük altında yeterliliği (ES 6 GB, worker 3 GB).
