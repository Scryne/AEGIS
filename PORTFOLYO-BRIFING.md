# AEGIS — Portföy Brifingi

> Bu dosya `C:\dev\portfolio\docs\brifing-prompt.md` içindeki çıkarma promptuna göre,
> kod tabanına bakılarak üretildi. Ölçüm tarihi: **2026-08-08**, `main` dalı,
> HEAD = `71e2832`, çalışma ağacı temiz (`git status --short` boş).
>
> Her sayının yanında kaynağı var. **"Ölçtüm"** = bu oturumda komut koşturuldu;
> **"koddan"** = dosya okunarak çıkarıldı. Bu ayrım her yerde korundu.
>
> Frontmatter'ın `slug` · `featured` · `order` · `diagram` · `cover` · `updated`
> alanları bilinçli olarak **boş**: bunlar portföy oturumunun kararı.

---

## 1. Künye

**Ne yapar.** Türkiye'deki MASAK yükümlüsü muhasebe ve denetim ofislerinin bir şirketi
müşteri olarak kabul etmeden önce yaptığı kimlik doğrulama ve yaptırım/PEP taramasını,
denetimde savunulabilir bir dosyaya dönüştüren çok kiracılı SaaS.

**Kimin için.** SMMM/YMM ve bağımsız denetim ofisleri (ROADMAP §1 "Anchor segment":
"SMMM/YMM and independent audit offices in Turkey (MASAK-obligated, short sales cycle,
manual today)"). Ürün içindeki RBAC rolleri de bu ofisin iç yapısını varsayıyor:
`owner` · `compliance_officer` · `analyst` · `auditor` (`CLAUDE.md`, RBAC bölümü).

**Çalışma dönemi.** 2026-07-22 → 2026-08-08 (ölçtüm: `git log --reverse` / `git log -1`).
Commit dağılımı (ölçtüm, `git log --date=format:"%Y-%m-%d %H:%M"`):

| Commit | Tarih/Saat | Kapsam | Değişim (ölçtüm, `--shortstat`) |
|---|---|---|---|
| `e803689` | 2026-07-22 12:33 | E1.1 platform iskeleti | 97 dosya, +12.539 |
| `f38b787` | 2026-07-23 15:22 | E1.2 uyum temeli | 34 dosya, +1.621 / −15 |
| `9593b4e` | 2026-08-08 12:23 | E1.3 tarama servisi | 55 dosya, +8.028 / −202 |
| `a0b6bcb` | 2026-08-08 16:34 | E1.4 varlık kütüğü | 54 dosya, +13.906 / −826 |
| `71e2832` | 2026-08-08 19:27 | E1.5 rapor & dosya | 37 dosya, +5.544 / −62 |

**Ara verilmiş dönem var:** 2026-07-23 ile 2026-08-08 arasında **16 gün** commit yok.

**Önemli uyarı — bu tablo çalışma temposunu ölçmez.** Geçmiş epic granülünde: her commit
bir epic'in tamamı. Son üç epic aynı günün 12:23–19:27 arasında, yaklaşık 7 saatlik bir
pencerede commit'lenmiş; ancak `+27.478` satırlık değişimin o 7 saatte *yazıldığı*
sonucu çıkarılamaz. Commit zamanı, işin yapıldığı zamanı değil paketlendiği zamanı
gösteriyor. Gerçek takvim yalnızca senin bildiğin bir şey — portföyde tarih verilecekse
oradan doğrulanmalı.

**Rol.** Tek geliştirici. `git shortlog -sn --all` (ölçtüm): `5  Scryne`.
Başka katkıda bulunan yok. Commit mesajlarında `Co-Authored-By: Claude Opus 5` trailer'ı
var (koddan, 5 commit'in tamamında) — yani iş **AI destekli** yazılmış; portföyde bunun
belirtilip belirtilmeyeceği senin kararın, ama commit geçmişinde açıkça duruyor.

**Yığın** (koddan: `pyproject.toml`, `package.json`, `infra/compose/docker-compose.yml`,
`CLAUDE.md` "Stack pins"). Mimariyi belirleyen 8 kalem:

1. **FastAPI (async)** + SQLAlchemy async + Alembic — API katmanı
2. **PostgreSQL 16 + Row Level Security** — çok kiracılılık DB seviyesinde zorlanıyor
3. **Next.js 16 (App Router) + React 19.2 + Tailwind** — SSR panel
4. **Celery + Redis** — tarama, günlük liste senkronu, belge çıkarımı
5. **yente 5.5.0 + Elasticsearch 9.4.2** — self-host yaptırım/PEP tarama motoru
6. **MinIO / S3-uyumlu nesne deposu** — belgeler DB'de değil burada
7. **xhtml2pdf + reportlab + python-docx** — PDF/Word rapor üretimi (yerel bağımlılık yok)
8. **Docling** — PDF belge çıkarımı, **opsiyonel** kurulum (yalnız worker imajında)

Python 3.12 · uv workspace (`aegis-core`, `aegis-api`, `aegis-worker`) · Node 22 ·
pnpm workspace (`@aegis/web`, `@aegis/api-client`).

**Satır ve dosya sayısı** (ölçtüm; `git ls-files` üzerinden, yani `node_modules`,
`.venv`, `__pycache__`, `.next` doğal olarak hariç):

| | Değer | Komut |
|---|---|---|
| İzlenen dosya | **200** | `git ls-files \| wc -l` |
| Kod satırı (py + tsx + ts) | **22.013** | `git ls-files '*.py' '*.tsx' '*.ts' \| xargs wc -l` |
| — Python | 18.716 | aynı, `*.py` |
| — TSX | 2.500 | aynı, `*.tsx` |
| — TS | 797 | aynı, `*.ts` |
| Test kodu (Python) | **4.586** (25 dosya) | `git ls-files '*test*.py' \| xargs wc -l` |
| Dokümantasyon (`.md`) | 2.132 | `git ls-files '*.md' \| xargs wc -l` |

Kilit dosyaları (`uv.lock`, `pnpm-lock.yaml`) sayımların dışında.

**Commit sayısı: 5** (ölçtüm, `git rev-list --count HEAD`).

---

## 2. Durum

### `geliştirme`

**Gerekçe.** Faz 1'in altı epic'inden **beşi bitmiş, altıncısına (E1.6 — üretim
dağıtımı + pilot onboarding) hiç başlanmamış** (`CLAUDE.md` "Epic status": E1.1 ✅,
E1.2 ~, E1.3 ~, E1.4 ~, E1.5 ✅, E1.6 ☐). Uygulama **hiç dağıtılmamış**, kullanıcısı yok,
`.env` dosyası çalışma ağacında bile mevcut değil (ölçtüm: `ls -la .env` → yok).

**Ölçülebilir ayrıntılar:**

- **250/250 birim testi geçiyor** (ölçtüm: `uv run pytest` → 4 satır nokta, `250 passed`,
  hata yok). Bunlar Docker gerektirmeyen katman: birim testleri + normalizasyon recall kapısı.
- **Toplam 359 test toplanıyor** (ölçtüm: `pytest --collect-only -q` → `359 tests collected`).
  Aradaki 109 test varsayılan koşuda işaretle ayrılıyor: **73 entegrasyon** (Docker/
  testcontainers, `-m integration`) + **36 uçtan uca tarama recall** (yente + ES,
  `-m screening`). **Bu 109'unu bu oturumda koşturmadım** — Docker ayağa kaldırılmadı.
- **Kodda tek bir `TODO`/`FIXME`/`HACK`/`XXX` yok** (ölçtüm: `git ls-files '*.py' '*.ts'
  '*.tsx' | xargs grep -cE "TODO|FIXME|HACK|XXX"` → eşleşen dosya sayısı 0). Yarım kalan
  işler koda not düşülmemiş; `CLAUDE.md`'deki epic listesinde açık madde olarak duruyor.
- **41 API yolu / 46 operasyon** üretilmiş ve commit'lenmiş OpenAPI şemasında
  (ölçtüm: `docs/openapi.json` üzerinden sayıldı).
- **5 Alembic migration** (0001 → 0005), **8 ADR**, CI'da **5 iş** (koddan:
  `migrations/versions/`, `docs/adr/`, `.github/workflows/ci.yml`).

**Neden "GA öncesi" değil:** dağıtım epic'i açılmamış; TLS, at-rest şifreli volume,
secret yönetimi (SOPS/age), VERBİS bildirimi E1.6'ya ertelenmiş durumda (`CLAUDE.md`,
E1.2 son madde). Neden "prototip" değil: RLS izolasyon kapısı, hash zincirli denetim izi,
%100 recall tabanı ve sözleşme drift kapısı CI'da bloke edici olarak koşuyor — prototip
disiplini bu değil.

**Açıkça yarım kalan üç şey** (koddan, `CLAUDE.md` epic listesindeki işaretsiz maddeler):

1. MASAK kaynak dosyasının sütun düzeni gerçek dosyayla doğrulanmadı (`COLUMN_ALIASES`).
2. Docling PDF yolu gerçek belgelerle denenmedi (düz metin yolu testlerde uçtan uca kapalı).
3. VKN sağlama basamağı resmî spesifikasyonla karşılaştırılmadı.

---

## 3. Problem

**README'nin tanımı** (`README.md:3-6`): Türkiye MASAK pazarında KYB / kurumsal durum
tespiti — şirketin kimliğini doğrula, kendisini ve kişilerini yaptırım/PEP/izleme
listelerine karşı **self-host yente** ile tara, denetim-kanıtlı ve kaynak bağlantılı bir
dosya üret.

**ROADMAP'in daha keskin tanımı** (`docs/ROADMAP.md` §1, §6/E0.1): hedef segment bugün bu
işi **elle** yapıyor; discovery script'i "current manual KYB/MASAK workflow, time per file,
tools used, **audit anxiety**" başlıklarını sorguluyor. Yani acı iki katmanlı: (a) dosya
başına harcanan zaman, (b) denetimde "bunu neye göre kabul ettin" sorusuna cevap
verememe korkusu.

**İkisi ayrışmıyor**, ancak kodda ROADMAP'in vurgusu baskın ve README'den ileri:
ürünün asıl iddiası "tarama yapmak" değil, **taramanın savunulabilir kaydını üretmek**.
Bu, koddaki üç yapının varlık sebebi:

- Denetim izi ekleme-yalnız (append-only) + kiracı başına **hash zinciri** (migration
  0002, `services/audit.py`)
- Her koşunun eşiklerini ve veri kümesi sürümlerini **satıra dondurması**
  (`ADR-0006` karar 1)
- Elenen eşleşmelerin **silinmeyip gerekçesiyle** dosyaya basılması (`ADR-0008` karar 4)

**Mevcut çözümler neden yetmiyor** — koddan çıkarılabilen kısım: ticari tarama API'leri
müşteri PII'sini dışarı gönderir; KVKK ve veri yerelliği bunu kapatıyor (`CLAUDE.md`
Invariant 3: "screening is the self-hosted yente instance **only**, never an external
screening API"). Bu, mimarinin en pahalı kararının doğrudan sebebi (bkz. Karar 1).
Segmentin bugünkü araçlarına dair başka bir iddia kodda **yok** — o veri E0.1 discovery
görüşmelerinden gelecek ve ROADMAP'te henüz işaretsiz.

---

## 4. Sistem

### Ana bileşenler ve sorumluluk sınırları

| Bileşen | Sorumluluk | Sınır (ne yapmaz) |
|---|---|---|
| `apps/api` (FastAPI) | HTTP, JWT, kiracı bağlamı, RBAC, doğrulama | İş kuralı barındırmaz; hesaplamayı `aegis_core`'a devreder |
| `packages/core` (aegis_core) | **Tüm iş mantığı**: modeller, tarama, kütük, risk kuralları, rapor, şifreleme, denetim | HTTP bilmez; `reports/risk.py` DB bile bilmez (dataclass alır) |
| `apps/worker` (Celery) | Derin tarama, günlük liste senkronu, belge çıkarımı, saklama süresi işi | Kendi iş mantığını yazmaz; `aegis_core` çağırır |
| `apps/web` (Next.js 16) | SSR panel, HITL inceleme ekranları | **Yetkilendirme yapmaz** — `proxy.ts` yalnız UX yönlendirmesi; gerçek authz backend JWT |
| yente + Elasticsearch | Yaptırım/PEP eşleştirme ve skorlama | Kiracı bilmez; kararı vermez, aday üretir |
| PostgreSQL 16 | Veri + **kiracı izolasyonunun kendisi** (RLS) | — |
| MinIO/S3 | Belgeler ve üretilmiş raporlar | — |

**"Her şeyi yapan" bileşen:** `packages/core` kasıtlı olarak geniş — 18.716 Python
satırının çoğu burada. API ince, worker ince. Bu bir tasarım kararı (paylaşılan kütüphane
deseni), ama portföyde "katmanlı mimari" diye sunulacaksa gerçeği söylemek gerekir:
çekirdek paket tek ve büyük bir kütüphane.

### Veri akışı

**Girdi.** (a) Elle giriş (`POST /entities`), (b) belge yükleme → MinIO → Türkçe çıkarım
→ `extraction_proposal` → **insan onayı** → kütük, (c) GLEIF'ten LEI zenginleştirme
(dışarı **yalnız LEI kodu** çıkar), (d) tarama koşusu (`POST /screenings` veya
`/screenings/from-entity/{id}`).

**Durma.** PostgreSQL: `entity` (kabul edilen değer) + `entity_attribute` (her gözlem,
kaynağı ve zamanıyla) + `screening`/`match_candidate` (koşu ve adaylar, eşikler dondurulmuş)
+ `discrepancy` + `audit_event` (ekleme-yalnız, hash zincirli) + `report`. Belgeler ve
üretilmiş raporlar MinIO'da; DB yalnız `sha256` ve `retention_until` tutar.

**Çıkış.** `GET /reports/risk/{entity_id}` (canlı, denetim olayı yazmaz) →
`POST /reports/dossier` → PDF veya Word, tek bir `DossierData`'dan üretilir, **önce nesne
deposuna sonra DB satırına** yazılır (depo yazımı başarısızsa satır yok), tam olarak bir
`report.export` denetim olayı, `source_ref = sha256:…`.

### Dış bağımlılıklar

- **PostgreSQL 16** (pgcrypto yok, `pg_trgm` var — bulanık ad eşleştirmesi için)
- **Redis 7** (Celery broker/backend + oran sınırlama)
- **Elasticsearch 9.4.2** (yente'nin indeksi; `ES_JAVA_OPTS=-Xms4g -Xmx4g`)
- **yente 5.5.0** (OpenSanctions eşleştirme motoru, self-host)
- **MinIO / S3-uyumlu** nesne deposu
- **GLEIF LEI API** (tek dış çağrı; sadece LEI gider, `GLEIF_ENABLED=false` ile kapanır)
- **MASAK malvarlığı dondurma listesi** (CSV → FtM dönüştürücü, özel yente veri kümesi)
- **Sentry** (opsiyonel; DSN boşsa tamamen kapalı)
- **LLM/AI servisi YOK** — Faz 1'de bilinçli olarak yok (`CLAUDE.md` Invariant 3)

**Ölçek notu (koddan, `CLAUDE.md` "yente/ES footprint"):** OpenSanctions belgelerine göre
ES indeksi **4–16 GB RAM + 10–30 GB SSD** ister. Tek hostun baskın maliyeti bu; 2–4 GB'lık
bir VPS yetmez. Bu ölçülmüş değil, upstream belgeden alınmış bir rakam.

### Diyagram kutuları (9 kutu — üst sınır)

```
1  Web (Next.js 16, SSR)          → 2
2  API (FastAPI, JWT + RLS bağlamı) → 3, 4, 6, 8
3  PostgreSQL 16 (RLS + denetim zinciri)
4  Redis (kuyruk)                 → 5
5  Worker (Celery + beat)         → 3, 6, 8, 9
6  yente 5.5.0                    → 7
7  Elasticsearch 9.4.2
8  MinIO / S3 (belge + rapor)
9  GLEIF LEI API (tek dış çağrı)
```

Vurgulanması gereken sınır: **6 ve 7 çevrenin içinde** — PII dış tarama API'sine
çıkmıyor. Diyagramda 9 numaralı kutu (GLEIF) çevrenin dışında ve oka "yalnız LEI kodu"
etiketi düşmeli; ürünün KVKK iddiası tam olarak bu iki detayda duruyor.

---

## 5. Kritik kararlar

### Karar 1 — Tarama motoru self-host (yente + Elasticsearch), dış API değil

- **Seçim.** OpenSanctions `yente` 5.5.0 + Elasticsearch 9.4.2 kendi ortamımızda; taranan
  ad/kimlik bilgisi hiçbir dış servise gitmiyor. Kaynak: `CLAUDE.md` Invariant 3,
  `ADR-0006`, `infra/compose/docker-compose.yml:161-234`.
- **Alternatif.** Ticari bir tarama API'si (ComplyAdvantage, Refinitiv World-Check ve
  benzeri) — entegrasyonu birkaç günlük iş, operasyon yükü sıfır.
- **Gerekçe.** KVKK ve veri yerelliği: müşterinin taradığı kişi verisi ofis ortamından
  çıkarsa ürünün "veri işleyen" konumu ve pilot sözleşmesindeki taahhüt bozulur. Ayrıca
  MASAK'ın kendi dondurma listesi özel bir veri kümesi olarak indekse enjekte edilebiliyor
  — dış API'de bu mümkün değil.
- **Bedel.** Tek hostun donanım maliyetini **bu tek karar belirliyor**: 4–16 GB RAM +
  10–30 GB SSD sadece ES indeksi için. Geliştirme ortamında da ağır — `docker compose`'da
  `--profile screening` arkasına alınmak zorunda kalındı, yani varsayılan geliştirme
  kurulumunda tarama **çalışmıyor**. CI'da ayrı bir iş (~1 GB heap) gerekti. Üstelik
  OpenSanctions verisinin ticari kullanım lisansı hâlâ açık bir kalem (ROADMAP E0.2,
  işaretsiz).

### Karar 2 — Kiracı izolasyonu PostgreSQL RLS'de, uygulama filtresinde değil

- **Seçim.** Her kiracıya-özel *veri* tablosunda `tenant_id` + `ENABLE`/`FORCE ROW LEVEL
  SECURITY`, `current_setting('app.current_tenant', true)::uuid` karşısında politika.
  Uygulama **süper-kullanıcı olmayan** `aegis_app` rolüyle bağlanıyor; migration'lar
  ayrıcalıklı `aegis` rolüyle. Bağlam yoksa `current_setting` NULL döner → **sıfır satır**
  (fail-closed). Kaynak: `ADR-0002`, `migrations/versions/0001_core_schema_rls.py`,
  `infra/compose/initdb/10-app-role.sql`.
- **Alternatif.** Her sorguya `WHERE tenant_id = :x` ekleyen bir uygulama katmanı
  (ORM mixin / repository deseni) — ya da kiracı başına ayrı veritabanı.
- **Gerekçe.** Uygulama filtresinde tek bir unutulmuş `WHERE` kiracı sızdırır ve bunu
  test etmek zordur. RLS'te unutmak imkânsız: politika yoksa bağlam da yok, sonuç sıfır
  satır. Kiracı başına DB ise tek geliştirici için migration ve yedek yükünü N'e çarpardı.
- **Bedel.** Üç somut maliyet: (a) kimlik/kontrol-düzlemi tabloları (`organization`,
  `user_account`, `membership`) **bilinçli olarak RLS-muaf** bırakılmak zorunda kaldı —
  login pre-auth çalışır, RLS altında fail-closed olup girişi kırardı; bu istisna ayrı
  gerekçelendirme ve ayrı bir "uygulama kodunda scope'lanır" kuralı doğurdu. (b) İki ayrı
  bağlantı dizesi (`DATABASE_URL` / `DATABASE_ADMIN_URL`) ve iki ayrı rol yönetilmek
  zorunda. (c) Yeni kiracı tablosu eklemek artık üç işlik bir iş: kolon + politika +
  izolasyon testine kayıt (`CLAUDE.md` Invariant 1'de kural haline getirilmiş; izolasyon
  kapısı E1.4'te 4 tablodan 10'a çıkarıldı — commit `a0b6bcb`).

### Karar 3 — Risk seviyesi **kural**, 0–100 puan değil

- **Seçim.** `reports/risk.py` şeffaf kurallar koşuyor: onaylanmış yaptırım eşleşmesi →
  Yüksek, onaylanmış PEP → Artırılmış, açık kritik tutarsızlık → Artırılmış. Seviye
  bulguların **maksimumu**; gizli ağırlıklandırma yok. Her bulgu düz Türkçe bir
  `rationale` taşıyor ve rapora basılıyor. Sıralama: `standard < unknown < elevated < high`.
  Kaynak: `ADR-0008` karar 1-3, `packages/core/src/aegis_core/reports/risk.py:59-69`.
- **Alternatif.** 0–100 arası ağırlıklı skor (planın ilk hâlinde ve rakiplerin çoğunda
  olan şey) — ekranda daha "ürün gibi" durur, sıralama ve önceliklendirme sağlar.
- **Gerekçe.** MASAK denetiminde sorulacak soru "bu dosyaya neden 72 dediniz". Ağırlıklı
  skor bunu cevaplayamaz; kural cevaplayabilir. Aynı gerekçe iki türev kararı da
  zorunlu kıldı: karara bağlanmamış yüksek skorlu eşleşme seviyeyi **yükseltmez**
  (`level=None`, yalnız `complete=False` yapar) — aksi "otomatik onay yok" değişmezini
  arka kapıdan delerdi; ve "sonuç yok" ≠ "temiz": tarama yoksa/başarısızsa seviye
  **Belirsiz**, asla Standart.
- **Bedel.** Ürün, dört kademeli kaba bir sinyal veriyor: iki "Artırılmış" dosya arasında
  hiçbir ayrım yok, sıralanamıyor, trend gösterilemiyor. Demoda rakibin skor göstergesi
  yanında zayıf görünür. Ağırlıklı/öğrenilmiş skor Faz 2'ye ertelendi ve bu erteleme
  ürünün en görünür eksiği.

### Karar 4 — Provenans **kolon değil gözlem** olarak modellendi

- **Seçim.** `entity` o an kabul edilen değeri tutuyor; `entity_attribute` **her gözlemi**
  kaynağı ve zamanıyla ayrı satır olarak tutuyor. Belgeden/kütükten gelen veri
  `promote_to_current=False` ile yazılıyor — müşterinin beyanını asla sessizce ezmiyor;
  çelişki bir `discrepancy` oluyor ve **zorunlu gerekçeyle** karara bağlanıyor, kapatılmıyor.
  Kaynak: `ADR-0007`, `migrations/versions/0004_entity_registry.py`, commit `a0b6bcb`.
- **Alternatif.** Klasik yol: `entity` tablosunda `tax_number`, `tax_number_source`,
  `tax_number_verified_at` gibi kolon üçlüleri. Çok daha az tablo, çok daha basit sorgu.
- **Gerekçe.** Kolonlarla karşılanamayan tek bir gereksinim vardı: tutarsızlık tespiti
  **aynı alanın birden çok gözlemini** ister — müşterinin beyan ettiği vergi numarası ile
  belgede yazan. Kolon modelinde ikincisini koyacak yer yok; koyulsa üçüncü kaynak
  (GLEIF) için yine yer yok.
- **Bedel.** Her okuma iki kaynağı birleştirmek zorunda (güncel değer + gözlem geçmişi);
  varlık detay ekranı ayrı bir provenans tablosu render etmek durumunda
  (`apps/web/src/app/(app)/entities/[id]/page.tsx:283-287`). Şema E1.4'te tek seferde
  altı kiracı tablosuna çıktı ve izolasyon kapısı 4'ten 10 tabloya genişledi. Basit bir
  "şirketin vergi numarası nedir" sorusu artık tek kolon okuması değil.

---

## 6. Zorlandığım yer

> **Kaynak sınırı — önce bunu söylemem gerek.** Geçmiş epic granülünde (5 commit).
> Bir şeyi geri alan commit, kısa aralıkla defalarca değişen dosya, terk edilmiş modül
> **yok** — çünkü tekil commit'ler yok. Dolayısıyla aşağıdaki olay, "önce/sonra diff'i"
> ile değil, **commit gövdesindeki itiraf ve koda düşmüş savunma** ile kanıtlanıyor.
> Portföyde anlatılacaksa kanıtın bu biçimde olduğu bilinmeli.

### Olay: şifrelenmiş kolon, şifrelenmemiş ikinci yoldan sızdı

**Nasıl fark edildi.** Bir test kırmızıya düştü. Commit `a0b6bcb` gövdesinde, kendi
cümlesiyle: *"including redaction of valid TCKNs found in extracted evidence text, which
otherwise leaked plaintext into an unencrypted column and into `role_title`* **(caught by
a test)**". İlgili test bugün hâlâ duruyor:
`apps/api/tests/integration/test_entities.py:103` — *"KVKK/ADR-0005: TCKN yanıtlarda düz
metin GÖRÜNMEZ."*

**Kök sebep — yanlış varsayım.** E1.2'de alan-düzeyi şifreleme mekanizması kuruldu
(AES-256-GCM, `SecretBox`/`EncryptedString`, `ADR-0005`) ve E1.4'te `entity.national_id`
kolonuna uygulandı. Varsayım şuydu: **"TCKN şifrelendi" demek, kolonu şifrelemek demektir.**
Yanlıştı. Aynı numara veritabanına ikinci bir yoldan giriyordu: belge çıkarımı, öneriyi
gerekçelendirmek için belgeden **serbest metin kanıt** alıyor (`extraction_proposal.evidence`)
ve yetki satırını `role_title` olarak kaydediyordu. Bu iki alan şifresiz. Yani imza
sirkülerinden okunan TCKN, şifreli kolonun yanı başında düz metin olarak duruyordu —
şifrelemeyi anlamsız kılarak.

İkinci, daha küçük bir hata da aynı yerden çıktı: `role_title` başlangıçta eşleşen satırın
**bağlamının tamamını** alıyordu, bu da kişinin adını ve kimlik numarasını unvan alanına
taşıyordu. Koddaki yorum bu acıyı hâlâ anlatıyor
(`packages/core/src/aegis_core/documents/extraction.py:325-328`): *"Bilinçli olarak yalnız
eşleşen satır döner: bağlamın tamamını almak, kişinin adını ve kimlik numarasını unvan
metnine taşıyordu — hem çirkin hem KVKK açısından yanlış."*

**Nasıl çözüldü.** `redact_national_ids()` yazıldı
(`packages/core/src/aegis_core/documents/extraction.py:308-321`) ve serbest metnin
kalıcılaştığı **her noktaya** uygulandı: satır 178 (kanıt metni), 333 (`role_title`),
379 (kişi kanıtı). Fonksiyonun tasarımındaki ince nokta, çözümün asıl işi:

```python
def _mask(match): 
    value = match.group(0)
    return "*" * (len(value) - 4) + value[-4:] if is_valid_tckn(value) else value
return re.sub(r"(?<!\d)\d{11}(?!\d)", _mask, text)
```

Yalnız **sağlama basamağı tutan** 11 haneli sayılar maskeleniyor. Gerekçe koda yazılmış:
vergi/MERSİS numaraları maskelenmiyor, çünkü onlar tüzel kişilerin kamuya açık
tanımlayıcıları ve **kanıtın okunabilirliği için gerekli**. Yani düzeltme "her sayıyı
yıldızla" kolaycılığına kaçmadı — TCKN sağlaması burada bir gizlilik filtresi olarak
ikinci kez kullanıldı.

**Sonrasında ne değişti.** Değişmezin ifadesi değişti. `CLAUDE.md`'deki E1.4 kuralı artık
"TCKN şifrelenir" demiyor; şunu diyor: *"Attribute rows, discrepancies, proposal evidence
and audit payloads carry only the **masked** form."* Yani koruma kolon seviyesinden **veri
akışı seviyesine** taşındı. Serbest metin, ayrı bir sızıntı yolu olarak tanındı — ve bu
tanıma E1.5'e de geçti: dosya raporunda TCKN maskeli basılıyor, vergi/MERSİS/LEI tam
(`ADR-0008` karar 6).

**Genellenebilir ders:** "Şu alan şifreli" bir kolonun özelliği değil, o verinin sistemdeki
**bütün yollarının** özelliği. Şifrelemeyi kolona uygulayıp bitti sanmak, sızıntıyı
şifrelemenin *yanına* park etmek demek.

### İkinci ve üçüncü aday (daha kısa, ama gerçek)

**`YENTE_AUTO_REINDEX=false` → `/readyz` sonsuza kadar 503.** Commit `9593b4e` gövdesi:
*"YENTE_AUTO_REINDEX must be true — when false yente skips even the **first** index and
/readyz stays 503 forever."* Varsayım "otomatik yeniden indeksleme kapalıysa ilk indeks
yine de kurulur, sonrası manuel olur" idi; yanlıştı, motor hiç indekslemiyor ve hazır
olduğunu hiç bildirmiyor. Düzeltme her iki compose dosyasına da yazıldı
(`docker-compose.yml:202`, `docker-compose.evals.yml:47`) ve `CLAUDE.md:268`'e uyarı
olarak not düşüldü.

**xhtml2pdf'in `@font-face` yolu Windows'ta `PermissionError` veriyor.** Bulgu
`packages/core/src/aegis_core/reports/render.py:17-20`'de: *"o yol fontu bir geçici dosyaya
kopyalayıp adıyla yeniden açar ve Windows'ta `PermissionError` verir (dosya hâlâ açıktır)."*
Bunun altında ondan da sinsi bir sorun vardı: reportlab'ın gömülü Type1 fontları WinAnsi
kodlamasında ve `ş ğ ı İ` harflerini **taşımıyor** — Türkçe rapor sessizce kutucuklarla
dolardı. Çözüm reportlab'ın kendi dağıtımıyla gelen Bitstream Vera TTF yüzlerini doğrudan
kaydetmek; ve testlerin üretilen PDF'ten **metni geri okuması** (`test_report_render.py`,
14 test) — "bu tür bir bozulma göze bakmadan fark edilmez" (ADR-0008 karar 5).

---

## 7. Ekran görüntüsü hazırlığı

### Yerelde ayağa kalkıyor mu?

**Denemedim.** Bu oturumda yalnız test paketi koşuldu (`uv run pytest` → 250 passed);
uygulama ayağa kaldırılmadı, Docker açılmadı, tarayıcıda hiçbir ekran görülmedi.
Bunu ölçüm diye sunamam.

Ayrıca çalışma ağacında **`.env` dosyası yok** (ölçtüm: `ls -la .env` → yok). Yalnız
`.env.example` var. Yani bu checkout'tan uygulama hiç çalıştırılmamış görünüyor —
en azından bu klasörde bir yapılandırma bırakılmamış.

Komut zinciri (koddan: `README.md:20-35`, `package.json` scripts):

```bash
cp .env.example .env               # AUTH_SECRET ve FIELD_ENCRYPTION_KEY doldurulmalı
uv sync
pnpm install
docker compose -f infra/compose/docker-compose.yml up -d postgres redis minio
uv run alembic upgrade head        # DATABASE_ADMIN_URL ile, senkron
pnpm run api:dev                   # http://localhost:8000  (/docs)
pnpm run web:dev                   # http://localhost:3000
pnpm run worker:dev                # Celery worker + beat (derin tarama, belge çıkarımı)

# Tarama ekranları için ek (AĞIR: ES 4 GB heap)
docker compose -f infra/compose/docker-compose.yml --profile screening up -d
```

`FIELD_ENCRYPTION_KEY` üretimi (`.env.example` içinde yazılı):
`uv run python -c "from aegis_core.security.encryption import generate_key; print(generate_key())"`

### Ön koşullar — hangileri olmadan açılmıyor

| Ön koşul | Olmadan ne olur | Kaynak |
|---|---|---|
| PostgreSQL 16 + `alembic upgrade head` | Hiçbir şey çalışmaz | `README.md`, `migrations/` |
| `aegis_app` rolü (compose initdb kurar) | RLS bağlantısı kurulamaz | `infra/compose/initdb/10-app-role.sql` |
| `AUTH_SECRET` | Giriş yapılamaz (prod'da fail-fast) | `.env.example` |
| `FIELD_ENCRYPTION_KEY` | TCKN yazan/okuyan her yol kırılır | `.env.example`, ADR-0005 |
| Redis | Derin tarama, günlük iş, oran sınırlama çalışmaz | `.env.example` |
| MinIO + bucket + anahtarlar | **Belge yükleme ve rapor dışa aktarma çalışmaz** (depo yazımı başarısızsa satır yazılmıyor) | ADR-0008 karar 7 |
| yente + Elasticsearch (`--profile screening`) | **Tarama ekranlarının hiçbiri dolmaz**; koşu `failed` olur, API 502 | ADR-0006 karar 3 |
| `YENTE_AUTO_REINDEX=true` | yente hiç indekslemez, `/readyz` sonsuza kadar 503 | `CLAUDE.md:268` |
| Docling (`uv sync --group extraction`) | **Zorunlu değil** — belge saklanır, çıkarım `skipped` olur, alanlar elle girilir | `.env.example`, CLAUDE.md E1.4 |
| GLEIF | Zorunlu değil — `GLEIF_ENABLED=false` ile kapanır | `.env.example` |
| Sentry | Zorunlu değil — DSN boşsa tamamen kapalı | `.env.example` |

**Ekran görüntüsü için pratik sonuç:** Giriş, panel, varlık ekranları için hafif kurulum
(Postgres + Redis + MinIO) yeter. **Tarama ekranları için ES'i ayağa kaldırmak şart** ve
bu makinede 4 GB heap demek. Ürünün en gösterişli ekranı, kurulumun en pahalı parçasının
arkasında.

### Demo veri var mı?

**Yok.** (ölçtüm: `ls scripts/` → yalnız `export_openapi.py` ve `masak_dataset.py`;
`git ls-files | grep -iE "seed|fixture|sample|demo"` → yalnız `evals/fixtures/entities.ftm.json`.)

`evals/fixtures/entities.ftm.json` bir seed değil: yente'ye indekslenen 34 varlıklık
**tarama tarafı** değerlendirme veri kümesi. Uygulama veritabanına hiçbir şey yazmaz.
Ancak ekran görüntüsü için **doğrudan işe yarar**: taranan şirket adı bu listeden seçilirse
gerçek bir eşleşme ekranı çıkar ve içindeki adlar uydurma (aşağıda).

**Üretmek ne kadar iş — bu bir tahmin, ölçüm değil.** API uçları hazır olduğu için seed
script'i düz bir HTTP zinciri: `POST /auth/register` → `POST /auth/login` →
`POST /entities` (birkaç şirket + kişi) → `POST /entities/{id}/relationships` →
`POST /screenings/from-entity/{id}` → birkaç `candidates/{id}/decision` →
`POST /reports/dossier`. 41 uçlu şemaya ve mevcut entegrasyon testlerindeki kurulum
koduna bakılırsa **yarım günlük** bir iş; entegrasyon testleri (`apps/api/tests/integration/`,
73 test) zaten bu akışları kuruyor, oradan kopyalanabilir. Belge yükleme ekranı için
ayrıca **uydurma bir imza sirküleri metni** gerekir — düz metin yolu çalışıyor, PDF
gerekmez.

### Anlamlı ekranlar (5 tane)

| # | Rota | Ne gösteriyor | Hangi iddiayı kanıtlıyor |
|---|---|---|---|
| 1 | `/screenings/[id]` | Tarama sonucu: aday listesi, skor, **"neden eşleşti" özellikleri**, eşik bandı, karar butonları | Ürünün çekirdeği. "Otomatik onay yok" burada görünür: yüksek skorlu aday `flagged` ama hâlâ `pending`, kararı insan veriyor |
| 2 | `/entities/[id]` | Risk paneli + kimlik + bağlar + belgeler + tutarsızlıklar + **provenans tablosu** ("her değerin kaynağı ve gözlem zamanı") | Karar 4'ün görsel karşılığı: hangi bilgi nereden geldi, kim beyan etti, belge ne diyor |
| 3 | `/audit` | Denetim izi listesi + **zincir doğrulama rozeti** (`GET /audit/verify`) | "Denetim-kanıtlı" iddiasının tek somut kanıtı. Hash zinciri bozulmamış diyen bir rozet, ekran görüntüsünde anlaşılır |
| 4 | Üretilmiş PDF dosya raporunun ilk sayfası | Risk seviyesi + düz Türkçe gerekçeler + elenen eşleşmeler + koşu anındaki eşikler/veri kümesi sürümleri | Müşterinin denetime götürdüğü *nesne*. Türkçe glyph'lerin doğru bastığını da gösterir (bkz. §6) |
| 5 | `/entities/[id]` üzerinde öneri inceleme (`proposal-review`) | Belgeden çıkarılan alanların **onay bekleyen** hâli, güven skorlarıyla | "Çıkarım kütüğe yazmaz, insan onaylar" (R2). Ürünün AI-otomasyon iddiası **yapmadığı** şeyle ayrışıyor |

İsteğe bağlı 6.: tarama motoru kapalıyken çıkan **"Tarama yapılamadı — sonuç YOK (temiz
değil)"** uyarısı. Portföyde alışılmadık ve ürünün duruşunu tek karede anlatan bir kare;
üstelik ES'i ayağa kaldırmadan alınabilir.

### Gerçek veri riski

**Bu projede risk düşük ama sıfır değil.**

- Demo veriyle doldurulmazsa ekranlar **boş** çıkar — kişisel veri görünmez, ama ekran da
  bir şey anlatmaz.
- **Gerçek dosyayla doldurulursa risk yüksektir:** ekranda gerçek şirket unvanı, vergi
  numarası, yetkili kişi adı ve `role_title` görünür. TCKN arayüzde ve raporda **maskeli**
  (son 4 hane) — bu koddan garanti. **Ad, vergi no ve MERSİS maskeli değil**, tam basılıyor
  (bilinçli: kamuya açık kütük numaraları). Yani "TCKN maskeli" güvencesi ekran görüntüsünü
  güvenli yapmaz.
- **Kural:** ekran görüntüleri yalnız uydurma verilerle. `evals/turkish_screening/cases.json`
  içindeki adlar (ABC Yapı, Yıldız İnşaat, Mavi Deniz Turizm, Ege Gıda, Kaya Kardeşler,
  Demir Çelik …) uydurma ve jenerik — ekran görüntüsü için güvenle kullanılabilir. Gerçek
  yaptırım listesindeki kişi adları **kullanılmamalı**: bir kişinin adını yaptırım eşleşmesi
  ekranında portföy sitesinde yayımlamak ayrı bir sorumluluk doğurur.
- `.env.example` gerçek sır içermiyor (dosyanın kendi başlığında yazılı); gitleaks CI'da
  bekçi olarak koşuyor.

---

## 8. Ölçülebilir ne varsa

Yalnız kanıtı olanlar. **"Ölçtüm"** = bu oturumda koşturuldu.

| Ölçüm | Değer | Kanıt |
|---|---|---|
| Birim test geçme oranı | **250 / 250** | **Ölçtüm:** `uv run pytest` → `250 passed`, 0 hata |
| Toplam toplanan test | **359** | **Ölçtüm:** `pytest --collect-only -q` → `359 tests collected` |
| — Entegrasyon (Docker) | 73 | **Ölçtüm:** `pytest -m integration --collect-only` (7 dosya: 4+2+16+23+1+8+19) |
| — Uçtan uca tarama recall | 36 | Aradaki fark (359 − 250 − 73); `CLAUDE.md:268` "36/36" diyor. **Bu oturumda koşturulmadı** |
| Türkçe recall tabanı | **%100** (34 vaka / 124 varyant) | **Ölçtüm:** `cases.json` → `cases: 34`, varyant toplamı 124, `distinct_pairs: 6`. Kapı: `evals/test_normalization_recall.py`, her push'ta bloke edici |
| Test kodu hacmi | 4.586 satır / 25 dosya | **Ölçtüm:** `git ls-files '*test*.py' \| xargs wc -l` |
| Kod satırı | 22.013 (py+tsx+ts) | **Ölçtüm:** `git ls-files … \| xargs wc -l` |
| İzlenen dosya | 200 | **Ölçtüm:** `git ls-files \| wc -l` |
| `TODO`/`FIXME`/`HACK` sayısı | **0** | **Ölçtüm:** `grep -cE "TODO\|FIXME\|HACK\|XXX"` → eşleşen dosya yok |
| CI iş sayısı | 5 | Koddan: `.github/workflows/ci.yml` — backend / screening-recall / contract / frontend / security |
| CI'daki bloke edici kapı sayısı | 4 | Koddan: normalizasyon recall · kiracı izolasyonu · uçtan uca tarama recall · OpenAPI sözleşme drift |
| Statik analiz | Ruff (lint+format) + **mypy strict** 3 pakette | Koddan: `ci.yml`, `package.json:typecheck:py` |
| API yolu / operasyon | 41 / 46 | **Ölçtüm:** `docs/openapi.json` üzerinden sayıldı |
| Migration sayısı | 5 (0001→0005) | Koddan: `migrations/versions/` |
| RLS korumalı tablo (izolasyon kapısında) | **10** | Koddan: commit `a0b6bcb` gövdesi — "isolation gate extended from 4 to 10 tables" |
| ADR sayısı | 8 | Koddan: `docs/adr/0001…0008` |
| Commit | 5 | **Ölçtüm:** `git rev-list --count HEAD` |
| Toplam eklenen satır (tüm geçmiş) | +41.638 / −1.105 | **Ölçtüm:** commit başı `--shortstat` toplamı |

**Kanıtı olmadığı için listelenmeyenler:** performans/gecikme ölçümü (tarama için NFR
"< 30 sn" hedefi `.env.example`'da yazılı ama **ölçülmemiş**), test kapsam yüzdesi
(coverage koşulmuyor), kullanıcı sayısı (yok), üretim uptime (dağıtım yok), ES indeks
boyutu (upstream belge rakamı var, kendi ölçümümüz yok).

---

## 9. Yayına çıkarma engelleri

**Senin karar vermen gerekenler — sıraya göre, en önemlisi üstte.**

1. **`AEGIS_Proje_Plani.docx` depoda commit'li** (32 KB, kök dizin). Bu bir **ticari iş
   planı**: ROADMAP'ten anlaşıldığı kadarıyla fiyatlama modeli, segment hipotezi, gelir
   projeksiyonu ve rekabet duruşu içeriyor. Depo public yapılacaksa bu dosya çıkarılmalı
   (ve geçmişten de temizlenmeli — ilk commit'te var). **İçeriğini okumadım**, karar senin.

2. **LİSANS DOSYASI YOK.** (ölçtüm: `git ls-files | grep -i licen` → sonuç yok;
   `pyproject.toml`'da `license` alanı yok.) Lisanssız yayımlanan kod varsayılan olarak
   "tüm hakları saklı"dır: kimse yasal olarak kullanamaz, ama sen de "açık kaynak"
   diyemezsin. Depo public olacaksa bilinçli bir lisans kararı gerekir. Yalnız vaka
   çalışması yayımlanacaksa sorun değil.

3. **OpenSanctions veri lisansı açık kalem.** ROADMAP E0.2'de "Request OpenSanctions
   commercial license quote" maddesi **işaretsiz**. OpenSanctions verisi ticari kullanımda
   lisans ister. Ekran görüntüsünde gerçek OpenSanctions kayıtları görünürse bu, ürünün
   veriyi ticari bağlamda kullandığını kamuya göstermek olur — lisans netleşmeden
   yapılmamalı. **Uydurma veri kümesiyle (`evals/fixtures/`) çekilen ekranlarda bu sorun yok.**

4. **`docs/legal/` ve `docs/kvkk/` taslak sözleşme metinleri içeriyor** (pilot sözleşmesi,
   DPA şablonu, aydınlatma metni, VERBİS hazırlığı). Gerçek isim/kurum yok — hepsi
   `{{ŞİRKET_UNVANI}}` gibi yer tutucu (koddan doğruladım). Ama pilot sözleşmesinin ticari
   şartları (ücretsiz pilot karşılığı vaka çalışması hakkı, sorumluluk sınırlaması)
   yayımlanınca müzakere pozisyonunu açık eder. Her metnin başında "v1 TASLAK — hukuki
   inceleme gerekir, bu hukuki tavsiye değildir" uyarısı var; yayımlanacaksa bu uyarının
   kırpılmaması önemli.

5. **KVKK/VERBİS yükümlülüğü henüz yerine getirilmemiş.** `CLAUDE.md` E1.2: "VERBİS filing
   (legal review + fill placeholders)" E1.6'ya ertelenmiş. Ürün "KVKK uyumlu" diye
   sunulacaksa bu ifadeye dikkat: **mimarisi** KVKK'yı gözetiyor (veri yerelliği, alan
   şifreleme, saklama süresi), ama **kurumsal uyum işlemleri** (VERBİS kaydı, hukuki
   inceleme) tamamlanmadı. "KVKK uyumlu bir ürün" ile "KVKK'yı gözeterek tasarlanmış bir
   mimari" arasındaki fark, bu vitrinde yanlış tarafa düşerse pahalıya mal olur.

6. **Müşteri işi değil, NDA yok.** Tek geliştiricinin kendi ürünü; `git shortlog` tek
   yazar gösteriyor, depoda müşteri adı geçmiyor. Bu yönden engel yok.

7. **Gömülü sır yok** (kontrol ettim): `.env` gitignore'da ve zaten mevcut değil,
   `.env.example` gerçek değer taşımıyor, CI'da gitleaks bekçi olarak koşuyor, `.gitignore`
   ayrıca `data/private/` altında "gerçek müşteri verisi ASLA commit edilmez" kuralını
   taşıyor. **Tam bir sır taraması yapmadım** — gitleaks'i bu oturumda koşturmadım;
   yayımdan önce bir kez `gitleaks detect` koşturmak ucuz sigorta.

8. **AI destekli geliştirme commit geçmişinde açık.** 5 commit'in tamamında
   `Co-Authored-By: Claude Opus 5` trailer'ı var. Portföyde tek geliştirici olarak
   sunulacaksa bu bir çelişki değil (araç kullanımı) ama depo public'se görünür bir gerçek;
   ne söyleneceğine önceden karar vermek, sonradan sorulmasından iyidir.

---

## Portföy oturumuna notlar

- **`slug`, `featured`, `order`, `diagram`, `cover`, `updated` boş bırakıldı** — brifing
  promptunun tarifi gereği bunlar site genelindeki sıralama ve dosya yolu kararı.
- **Kademe önerisi (senin kararın, ama gerekçemle):** tam vaka çalışması. Sebep, ürünün
  kendisi değil **kararların dokümante edilmiş olması**: 8 ADR, her biri alternatifi ve
  bedeliyle. §5'teki dört kararın dördü de bedeliyle birlikte kodda kanıtlanabiliyor —
  kompakt liste kaydı bunu ziyan eder.
- **En güçlü anlatı ekseni:** "yanlış negatif bu üründeki tehlikeli hata" cümlesi kod
  tabanında en az dört ayrı yerde tekrar ediyor (`normalization.py` başlığı,
  `topics.py` başlığı, `evals/README.md`, `ci.yml` yorumu) ve mimarinin dört ayrı
  kararını tek başına açıklıyor: %100 recall tabanı, ASCII üzerinden ek eşleştirme,
  önek eşleşmeli topic yüklemi, "sonuç yok ≠ temiz". Vaka çalışmasının omurgası bu olabilir.
- **Kaçınılması gereken cümle:** "AI destekli uyum platformu". Faz 1'de **hiç LLM çağrısı
  yok** ve bu bilinçli bir değişmez (`CLAUDE.md` Invariant 3: "No LLM calls in Phase 1").
  Ürünü olduğundan farklı göstermek, §2'deki dürüstlük kapısını da geçersiz kılar.
