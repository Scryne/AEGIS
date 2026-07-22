# ADR-0002: Çok-kiracılılık — tenant_id + PostgreSQL RLS

- **Durum:** Kabul edildi
- **Tarih:** 2026-07-22
- **Karar veren:** Scryne

## Bağlam
AEGIS hassas kurumsal/kişisel veri işler; kiracılar arası veri sızıntısı en kritik
tehdittir (Ürün Planı §8, KVKK). İzolasyon yalnızca uygulama katmanına bırakılamaz —
tek bir kod hatası tüm izolasyonu bozmamalıdır. Bu, ürünün ana invariant'ıdır ve ilk
migration'dan itibaren geçerlidir (canlı pilot verisine sonradan RLS eklemek en pahalı
hatadır).

## Karar
Kiracıya-özel her **veri** tablosu bir `tenant_id` taşır; **PostgreSQL Row-Level
Security (RLS)** politikaları her sorguyu aktif kiracıyla sınırlar. Uygulama her
transaction'da aktif `tenant_id`'yi `app.current_tenant` GUC'una **transaction-local**
yazar; RLS bunu zorunlu kılar.

**Kritik uygulama detayları:**
1. Kiracı-özel tablolarda `ENABLE` + **`FORCE ROW LEVEL SECURITY`** (sahip rolü dahil
   kimse baypas edemez).
2. Uygulama (api/worker) **süper-kullanıcı olmayan** `aegis_app` rolüyle bağlanır;
   migration'lar ayrıcalıklı `aegis` rolüyle çalışır (`DATABASE_URL` vs
   `DATABASE_ADMIN_URL`). Süper-kullanıcı RLS'yi baypas ederdi.
3. Politika ifadesi **`NULLIF(current_setting('app.current_tenant', true), '')::uuid`**
   kullanır. Sebep: bağlam hiç ayarlanmamışsa `current_setting(..., true)` NULL döner;
   ama aynı oturumda daha önce (transaction-local) ayarlanıp geri alınmışsa GUC boş
   STRING'e döner ve `''::uuid` **hata** verirdi. `NULLIF` boş string'i NULL'a çevirir →
   hiçbir satır eşleşmez → nazik **fail-closed** (hata fırlatmadan sıfır satır).

**Kimlik / kontrol-düzlemi istisnası:** `organization`, `user_account`, `membership`
RLS **taşımaz**. Bunlar kayıt/giriş sırasında (henüz tenant bağlamı yokken) *no-tenant*
oturumla sorgulanır; RLS onları fail-closed yapıp login'i kırardı. Bu tabloların uçları
kiracıyı **uygulama katmanında** `principal.tenant_id` ile sınırlar. İzolasyon garantisi
her tenant-scoped **veri** tablosunun RLS'inde durur (ilki: `tenant_setting`).

**Kural (çift katman + test):** Yeni bir kiracı-özel veri tablosu eklenirken `tenant_id`
+ RLS politikası + kiracılar-arası izolasyon iddiası **aynı commit'te** eklenir.

## Sonuçlar
**Olumlu:** Güçlü, veritabanı-düzeyinde izolasyon; tek şema ile düşük operasyonel yük.
CI'daki izolasyon kapısı (API uçları + app rolü altında doğrudan SQL) her push'ta koşar.
**Ödünler:** Her veri tablosunda RLS disiplini; oturum değişkeni yönetimi ve testi
zorunlu. Kimlik tablolarının uygulama-katmanı sınırlaması bilinçli, dar bir istisnadır.

## Alternatifler
- **Şema/DB-per-tenant:** Daha güçlü izolasyon, yüksek operasyon; çok duyarlı kurumsal
  müşteriler için ileride yükseltme yolu olarak açık tutulur (Faz 4).
- **Yalnızca uygulama-katmanı filtreleme:** Tek hata noktası; kabul edilemez.

## İlgili
Ürün Planı §6.3, §8; CLAUDE.md (invariants); `migrations/versions/0001_core_schema_rls.py`;
`apps/api/tests/integration/test_isolation.py`.
