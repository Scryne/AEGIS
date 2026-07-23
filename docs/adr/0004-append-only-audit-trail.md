# ADR-0004: Append-only denetim izi + kiracı-başına hash zinciri

- **Durum:** Kabul edildi
- **Tarih:** 2026-07-23
- **Karar veren:** Scryne
- **İlgili:** CLAUDE.md Invariant 2; ADR-0002 (RLS); ROADMAP §7 E1.2

## Bağlam
AEGIS bir uyum ürünüdür: MASAK yükümlüsü ofisler, kararlarını denetime karşı
belgelemek için kullanır. Denetim izinin **değiştirilemez** ve **kurcalamaya-dayanıklı**
olması ürünün temel değer önermesidir. İz, ilk pilot verisi oluşmadan **önce** doğru
kurulmalıdır (canlı veriye sonradan append-only + hash zinciri eklemek pahalıdır).

## Karar
Risk-etkileyen her eylem (tarama çalıştırma, eşleşme onay/ret, rapor dışa aktarma,
varlık düzenleme; şimdilik ayar güncelleme) `audit_event` tablosuna **tam bir** olay
yazar. Tablo kiracıya-özel bir *veri* tablosudur → `tenant_id` + ENABLE/FORCE RLS
(Invariant 1). Değiştirilemezlik ve kurcalama tespiti iki mekanizmayla sağlanır:

**1. Append-only — çift katman.**
- `aegis_app` (uygulama rolü) `audit_event` üzerinde UPDATE/DELETE yapamaz (migration
  0002'de REVOKE; initdb blanket grant'ini bu tablo için geri alır).
- Rolden bağımsız bir `BEFORE UPDATE OR DELETE` trigger'ı her mutasyonu `RAISE` ile
  reddeder — superuser dahil. Böylece INSERT serbest, geçmiş dokunulmazdır.

**2. Kurcalamaya-dayanıklılık — kiracı-başına hash zinciri.**
- Her olay `seq` (kiracı başına 1'den monotonik) ve iki hash taşır:
  `row_hash = SHA256(canonical(seq, aktör, eylem, hedef, kaynak, payload, occurred_at, prev_hash))`,
  ilk halkada `prev_hash = GENESIS_HASH` (64 sıfır).
- `verify_chain` tüm zinciri baştan yeniden hesaplar; tek alan değişse ilgili halka
  tutmaz. Trigger'ı devre dışı bırakabilen bir DBA bile geçmişi **sessizce**
  değiştiremez — verifier kopuşu bildirir (`GET /api/v1/audit/verify`).
- Zincir yazımı kiracı başına bir **transaction-scoped advisory kilit** ile seri hale
  gelir; `seq`/`prev_hash` ataması yarışmaz. `UNIQUE(tenant_id, seq)` DB düzeyinde
  emniyet kemeridir. Olay, denetlenen iş değişikliğiyle **aynı transaction**'da commit
  olur (atomik).

**Tasarım notları / bilinçli seçimler:**
- `actor_user_id` FK **taşımaz**: kullanıcı sonradan silinse de iz aktörü korur.
- `tenant_id` FK'i `ON DELETE CASCADE`tir (TenantMixin); ama append-only trigger'ı
  cascade DELETE'i de reddeder → **denetim geçmişi olan bir organizasyon silinemez**.
  Bu, bilinçli bir uyum duruşudur (imha, E3.7'de ayrı ve ayrıcalıklı bir süreçtir).
- `payload` JSON round-trip'e dayanıklı olmalıdır (Decimal/NaN değil); yazım ve
  doğrulama tek `_compute_row_hash` yolunu kullanır → biçim kayması olamaz.
- `occurred_at` hash'e dahildir ve determinizm için Python'da (UTC) üretilir.

## Sonuçlar
**Olumlu:** DB-düzeyinde değiştirilemezlik + matematiksel kurcalama tespiti; her ikisi
de CI entegrasyon testleriyle kapıya bağlıdır (izin katmanı, trigger katmanı, DBA
kurcalama simülasyonu, kiracı izolasyonu, RBAC). Uyum anlatısı güçlüdür.
**Ödünler:** Her risk-etkileyen eylemin bir olay yayması disiplini; olay yayımı
transaction'a girdiğinden başarısız yayım iş değişikliğini geri alır (istenen davranış).
Advisory kilit, kiracı başına denetim yazımını serileştirir — pilot ölçeğinde önemsiz.

## Alternatifler
- **Yalnız trigger (hash yok):** DBA kurcalamasını yakalayamaz; uyum vaadi zayıflar.
- **Harici WORM/nesne deposu:** Operasyonel yük yüksek; tek-host solo duruşuyla (R6)
  çelişir. Zincir, aynı Postgres içinde eşdeğer tespit sağlar.
- **Global (kiracılar-arası) tek zincir:** İzolasyonu bozar ve yazım darboğazı yaratır.

## İlgili
CLAUDE.md (Invariant 2); `migrations/versions/0002_audit_event.py`;
`packages/core/src/aegis_core/services/audit.py`;
`apps/api/tests/integration/test_audit_trail.py`.
