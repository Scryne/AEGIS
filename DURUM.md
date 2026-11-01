# DURUM — AEGIS — MASAK/KYB due diligence

> **Ne bu dosya:** sertifika değil **envanter**. Ölçülen gerçek durum; "çalışmıyor" yazan satır
> kusur değil, kayıt. Kapanış standardı: `ScryneOS/🎯 100-Command-Center/Kapanis-Standardi.md`

**Ölçüm tarihi:** 2026-09-26 (önceki: 2026-08-27)
**Tek cümle:** İlk kez uçtan uca çalıştırıldı (API + Celery worker + Docling + yente + web);
259 birim + 79 izolasyon/entegrasyon + 36 uçtan uca recall testi yeşil, bağımlılık açığı 0.

## 2026-11-01: E3.7 sertleştirme (yerel kısım)

- Yetki taraması (otomatik, OpenAPI'den): her /api/v1 ucu kimliksiz 401; denetçi hiçbir yazma ucunda
  2xx alamıyor. İlk yazımda tarama 0 uç görüyordu (bu FastAPI sürümü router'ları sarmalıyor) ve boşuna
  geçiyordu; alt sınır kontrolü yakaladı, şemadan okumaya geçildi.
- pip-audit: pypdf 6.21.2'de 7 açık → 6.21.4. gitleaks: 31 commit, sızıntı yok.
- 1.000 satırlık toplu iş: 20,8 sn, tüm satırlar sonuçlandı, kota = taranan satır (`scripts/load_batch_1k.py`).
- Saklama: günlük görev kuru çalışma rapor moduna geçti (kiracı ve tablo başına aday, denetim olayı,
  silme yok). İşletim el kitabı `docs/runbook.md`.
- Sunucu gerektiren (açık): 50 eşzamanlı kiracı yük testi, ES yeniden indeksleme tatbikatı.

## 2026-11-01: E3.5 kullanım ölçümü iskeleti (ADR-0018)

- Kullanım kaynağa göre (ekran / API / toplu), %80 uyarısı, ay sonu dökümü (`usage_statement`, göç
  0016, RLS, worker her gün önceki dönemi kapatır, idempotent). Plan sayfasında döküm ve dönemler.
- Bulunan hata düzeltildi: motora ulaşılamayan tarama kotadan düşüyordu (toplu işin yeniden
  denemesinde aynı satır iki kez sayılıyordu). Kota sayacı ve döküm artık `failed`ı saymıyor;
  sabotajla sınandı.
- Açık (Scryne): fiyat, ödeme sağlayıcısı, tahsilat takibi, gelir panosu.

## 2026-11-01: E3.6 eşleşme kalitesi programı (ADR-0017)

- İnsan kararlarından yanlış pozitif ve inceleme oranı, işaret isabeti/duyarlılığı; otomatik
  elenenler ayrı sayılır (doğrusu bilinmez). Eşik taraması + güvenli öneri (≥ 30 karar, 0,05 pay;
  eşiği insan değiştirir). Olumsuz haber isabeti ve puana alınma ön koşulu. Haftalık worker + elle
  kayıt → eğilim (`match_eval_run`, göç 0015, RLS, izolasyon kapısında).
- Testler: birim 7 + entegrasyon 2; tüm paket yeşil. Canlı (aegis_dev): 6 demo kararıyla /quality
  sayfası, grafik, eğilim; 1440/390 taşma ve konsol hatası yok.
- Açık: gerçek kararlar birikince en az iki ayar turu (çıkış ölçütü 5); embedding kapısı veri bekliyor.

## 2026-11-01: E3.4 genel API — API anahtarı + webhook (ADR-0016)

- API anahtarı: rol kapsamlı (analist/denetçi; karar rolleri anahtara verilmez), yalnız özet
  saklanır, bir kez gösterilir, iptal anında etkili, anahtar başına dakikada 120 istek, taramalar
  kotaya sayılır. `X-API-Key` ya da `Bearer aeg_…`.
- Webhook: giden kutusu (işle aynı transaction), worker 30 sn'de bir teslim, HMAC imza,
  30 sn → 6 sa yeniden deneme, `dead` + elle yeniden gönderim, sır yenileme, test (ping), teslim
  kaydı. Yük kişisel veri taşımaz. SSRF: https + herkese açık adres, kayıtta ve her teslimde.
- Belge: `docs/api/README.md` (Türkçe hızlı başlangıç, Python/Node imza doğrulama), Postman
  koleksiyonu şemadan üretilir. Göç 0014 (`api_key` kimlik denetim düzlemi; webhook tabloları RLS).
- Testler: birim 12 + entegrasyon 4; tüm paket yeşil; 8/8 sabotaj (ilk turda kaçan 2 için test
  eklendi). Canlı (aegis_dev): Entegrasyonlar sayfasında anahtar açıldı, terminalden anahtarla
  /cases /batches /screenings 200, yönetim ucu 403, iptal → 401; iç ağ adresli webhook arayüzde
  doğru mesajla reddedildi. Dışarı istek atabilecek gerçek webhook bilinçli olarak eklenmedi.
- Not (demo verisi): aegis_dev'deki kurgusal kişi kaydının TCKN'si bilinen iki anahtarla da
  açılmıyor (eski bir oturumun geçici anahtarı); /entities bu DB'de 500 veriyor. Ürün bilinçli
  olarak kapalı başarısız oluyor; demo kaydı silinmedi.

## 2026-11-01: E3.3 toplu tarama (ADR-0015)

- CSV (UTF-8/Windows-1254, `;`/`,`), durumsuz önizleme + önerilen sütun eşlemesi, TCKN sütunu
  reddedilir; satırlar ER'den geçer (mevcut / yeni / belirsiz → insana), sonra elle taramayla aynı
  yol. Worker 25'lik parçalar, satır başına alt işlem, `SKIP LOCKED`, yeniden deneme; kota başlatırken.
- Sonuç: riske göre sıralı, süzgeçler, toplu vaka/izleme, Excel'e uygun CSV özet (formül korumalı).
  Göç 0013 (`screening_batch`, `screening_batch_row`, RLS, izolasyon kapısında).
- Testler: birim 10 + entegrasyon 4 yeni, tüm paket yeşil; 7/7 sabotaj yakalandı.
- Canlı (aegis_dev): 8 satırlık kurgusal CSV arayüzden yüklendi, eşleme önerisi doğru, başlatıldı.
  Bu makinede yente yok: "şimdi işle" satırları "yeniden denenebilir" diye düşürdü (doğru davranış),
  yeniden deneme + taklit motorla 6/6 tarandı, yaptırım satırı en üstte, toplu vaka açıldı, CSV indi.
  Görülen iki kusur düzeltildi: yeniden denemede eski hata metni kalıyordu; tümü başarısızken başlık
  yalnız "Tamamlandı" diyordu. 1440/390 taşma yok.

## 2026-11-01: Phase 3 — E3.1 tam izleme çekirdeği + E3.2 vaka yönetimi (ADR-0014)

- Alarm derecesi (yaptırım → kritik, PEP / onaylı eşleşmenin düşmesi → yüksek), alarm anında risk
  puanı kaydı (önce/sonra alarmda), kritik/yüksek alarm vaka açar (kritik → EDD listesiyle; alarm
  başına tek vaka, tekillik kısıtı). Göç 0012: `compliance_case` + `case_comment` (RLS, izolasyon
  kapısında), alarm `severity`/`reassessment`.
- Vaka: durum makinesi (analist yükseltir, karar uyum uzmanının), gerekçe zorunlu, EDD tamamlanmadan
  karar yok, karar anında puan yeniden kayda geçer; atama, son tarih, yorum; geçmiş denetim izinden.
- Phase 3 çıkış ölçütü 1 testte uçtan uca: veri değişikliği → kritik alarm → EDD vakası → kapanış →
  puan yükseldi (`case_decision`). Birim 13 + entegrasyon 4 yeni, tüm paket yeşil; 8/8 sabotaj
  yakalandı; göç ileri-geri-ileri temiz.
- Canlı (aegis_dev, taklit yente ile kurgusal iki şirket): /monitoring derece + puan + vaka bağı,
  /cases kuyruğu, vaka ayrıntısında atama → inceleme → EDD kapısı (409 mesajı) → madde → kapanış;
  1440 ve 390'da taşma yok. Not: API Windows'ta Selector döngüsüyle başlatılmalı (psycopg async).
- Açık: sicil/gazete ve olumsuz haber yeniden kontrolü (kaynak yok), yönlendirme/özet (e-posta yok).

## 2026-11-01: E2.5 olumsuz haber betası (ADR-0013)

- Kapsam yol haritasının zaman kutusu kuralıyla: toplama + elle ayıklama; LLM hattı Phase 3'e.
  Kaynak Google News RSS (tr-TR): kamuya mal olmuş bir isimde iki sorgu 30+30 sonuç, hedefli sorgu
  olumsuz başlıkları getirdi (canlı ölçüm). GDELT bu ağdan oran sınırında.
- `adverse_media_item` (göç 0011, RLS, izolasyon kapısında); beta bayrağı sahipte; 5 dk oran
  sınırı; "ilgili/ilgisiz" kararı gerekçeli ve denetimli; risk puanına girmez.
- Testler: birim 4, entegrasyon 2 yeni; tüm paket yeşil. Beta kapısı mutasyonla kaldırılınca test
  düşüyor. Testte bulunan gerçek hata: Türkçe karakterli User-Agent uygulama açılışını düşürüyordu.
- Canlı (aegis_dev): Plan sayfasından beta açıldı, varlık sayfasında tarama çalıştı (kurgusal demo
  şirketine haber yok → "Bu adla haber bulunamadı"); 1440/390 taşma 0, konsol 0. Demo'ya gerçek
  kişi kaydı bilinçli olarak eklenmedi.

## 2026-11-01: E2.6 plan ve kota (ADR-0012)

- Kiracı planı `organization.plan_code` (göç 0010), katalog kodda (pilot / standart / kurumsal),
  atama `scripts/plan_ata.py`. Kullanım = Türkiye takvim ayında kullanıcının başlattığı
  taramalardaki özne sayısı; gece izlemesi sayılmaz.
- Senkron, varlık ve derin tarama uçlarında kota kapısı: aşım izni olmayan planda 402
  `quota_exceeded`, kısmi tarama yok, kiracı satırı kilitli. İzlemeye almada plan sınırı 409.
- Testler: entegrasyon 2 + birim 3 yeni; tüm paket yeşil. Kota kapısı mutasyonla kaldırılınca test
  düşüyor. Canlı (aegis_dev): `/billing/usage` ve "Plan ve kullanım" sayfası 1440/390 taşmasız;
  web'deki eksik favicon (404) eklendi.
- Kod dışı (Scryne): fiyat, ödeme kanalı (iyzico/PayTR), abonelik sözleşmesi, pilot dönüşümü.

## 2026-11-01: E2.2 ŞİB taslağı (ADR-0011)

- Form alanları MASAK'ın SM/SMMM/YMM rehberinden (MSK-RHB-ŞİB-018-1.0, 16.06.2025, §4.2 A–G) ve
  SK tablosundan (41 kod) birincil kaynakla teyit edildi; 10-31'de teyit olmadığı için yazılmamıştı.
- Dosyadan ön doldurma (kimlik, gerçek faydalanıcılar, risk bulguları); kategori/SK/işlemler boş
  (yükümlünün kararı); iskelet açıklama değiştirilmeden dışa aktarılamaz. Word çıktısı A–G sırasında,
  gizlilik ibareli. Yalnız sahip/uyum görevlisi; form şifreli (göç 0009, RLS), denetim izi içeriksiz.
- Testler: birim +17, entegrasyon +5 (izolasyon kapısına `sib_draft`); 5/5 mutasyon. Gerçek API + web
  turu: aç → düzenle → kaydet → Word indir, 1440/390 taşmasız.
- Açık: pilot uyum görevlileriyle gerçek bildirime karşı doğrulama; 10 iş günü süresi yalnız ikincil
  kaynakta teyitli (sayaç eklenmedi).

## 2026-10-31: Phase 2 başladı — E2.1 gerçek faydalanıcı (UBO)

- **Hesap:** saf çekirdek (`aegis_core.ubo.compute`) + özyinelemeli CTE ile zincir toplama +
  `ubo_computation` anlık görüntüsü (migration 0006, RLS, saklama, girdi özeti) + `ubo.compute`
  denetim olayı. Katman çarpımı, çapraz pay, döngü (açıkça raporlanır), yabancı/ortaksız tüzel
  kişi, eksik pay, kontrol → üst düzey yönetici dayanağı. Eşik varsayılanı "%25'ten fazla",
  kapsayıcı yorum seçilebilir (ADR-0009).
- **API:** `POST/GET /entities/{id}/ubo`, `/ubo/history`; taranmamış UBO'lar yanıtta.
- **Arayüz:** şirket sayfasında "Gerçek faydalanıcı" paneli — katmanlı sahiplik grafı (UBO yolları
  ana renkte, döngü kesikli kırmızı, çözülemeyen düğüm kesikli sarı), yollar, belirsizliğin nedeni,
  tek tıkla tarama. Gerçek API + web ile 1440/390'da doğrulandı, taşma 0, hata 0.
- **Testler:** birim 273 (+14 UBO), entegrasyon 83 (+4 UBO; izolasyon kapısına `ubo_computation`
  eklendi). Docker'sız çalıştırma: `AEGIS_TEST_PG_SERVER` + `AEGIS_TEST_REDIS_URL`.
- **E2.3 açıklanabilir risk puanı:** sabit ağırlıklı faktör modeli (v1, ADR-0010), her faktör gerekçe
  + dayanak bağlantısıyla; canlı puan yazmaz, "kayda geçir" ve UBO hesabı `risk_score_snapshot`'a
  (göç 0007, RLS) yazar, zaman çizelgesi yalnız değişimleri taşır. Şirket sayfasında puan paneli
  (1440/390 doğrulandı). Yüksek riskli ülke listesi yapılandırmadan (`HIGH_RISK_COUNTRIES`, boş).
- **E2.4 izleme-lite:** varlıkta `monitored` bayrağı (göç 0008), gece 02:45 UTC görevi (senkrondan
  sonra) izlenen varlıkları elle taramayla aynı çekirdekle (`screening.entity_run`) yeniden tarar;
  önceki koşuyla yapısal fark (yeni eşleşme / onaylı eşleşme çıktı / konu değişti; insanın daha önce
  elediği kayıt "yeni" sayılmaz) → `monitoring_alert` (RLS) + denetim olayı. "İzleme" sayfası ve
  varlık sayfasında anahtar; onay gerekçe ister. Sahte yente ile canlı API+web'de doğrulandı.
  E-posta kanalı yok (projede SMTP altyapısı yok).
- **Testler:** birim 290 (+9 puan, +8 fark), entegrasyon 87 (+2 puan, +2 izleme; izolasyon kapısına
  `risk_score_snapshot`, `monitoring_alert`).
- **Açık:** ortaklık tablosunun belgeden çıkarımı, pilot dosyalarda doğrulama, dosya raporunda puan
  sayfası. E2.2 (ŞİB taslağı), E2.5 (olumsuz haber), E2.6 (ödeme) başlamadı.

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
