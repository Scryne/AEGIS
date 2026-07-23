# Kişisel Veri İşleme Envanteri (v1)

> ⚠️ **v1 TASLAK — hukuki inceleme gerekir.** VERBİS kaydı ve iç politika için temel
> alınır; `{{...}}` doldurulmalı, hukukçu/DPO onayı alınmalıdır.

Bu envanter, AEGIS'in **veri sorumlusu** sıfatıyla işlediği verileri (platform
kullanıcıları) ayrıntılandırır. AEGIS'in **veri işleyen** olduğu müşteri-verisi
işleme faaliyetleri, ayrım için ayrı bir tabloda özetlenir (aydınlatma müşteriye aittir).

## A. AEGIS = Veri Sorumlusu (platform kullanıcıları)

| # | Faaliyet | Veri kategorisi | İlgili kişi grubu | Amaç | Hukuki sebep (m.5) | Alıcı grubu | Saklama | Yurt dışı |
|---|---|---|---|---|---|---|---|---|
| 1 | Hesap/kimlik yönetimi | Kimlik, iletişim | Ofis kullanıcıları | Kayıt, giriş, yetkilendirme | Sözleşme (5/2-c) | — (dahili) | İlişki + {{SAKLAMA_YILI}} yıl | Hayır |
| 2 | Kimlik doğrulama | İşlem güvenliği (parola özeti, token, rol) | Ofis kullanıcıları | Erişim kontrolü, RBAC | Sözleşme (5/2-c) | — | İlişki süresi | Hayır |
| 3 | Güvenlik/kötüye kullanım önleme | Bağlantı verisi (IP), oran-sınır sayaçları | Ofis kullanıcıları | Brute-force/istismar önleme | Meşru menfaat (5/2-f) | — | Kısa (sayaç: dakikalar) | Hayır |
| 4 | Denetim izi | İşlem kayıtları (aktör, eylem, hedef, zaman, kaynak) | Ofis kullanıcıları | Hesap verebilirlik, yasal yükümlülük | Hukuki yükümlülük (5/2-ç) | Denetçi (salt-okunur) | ≥{{SAKLAMA_YILI}} yıl (append-only) | Hayır |
| 5 | Destek | İletişim + talep içeriği | Ofis kullanıcıları | Destek sunma | Sözleşme/meşru menfaat | — | Talep + makul süre | Hayır |

## B. AEGIS = Veri İşleyen (müşteri adına — özet)

> Bu faaliyetlerde **veri sorumlusu müşteridir**; AEGIS müşterinin talimatıyla işler.
> Aydınlatma, hukuki sebep tayini ve ilgili kişi başvurusu **müşterinin** yükümlülüğüdür;
> AEGIS teknik/organizasyonel tedbirlerle destekler ([DPA](../legal/dpa-sablonu.md)).

| # | Faaliyet | Veri kategorisi | Amaç | Teknik tedbir | Yurt dışı |
|---|---|---|---|---|---|
| 6 | Şirket profili & doğrulama | Kimlik/ticari (unvan, vergi no, MERSIS, adres, yöneticiler) | KYB/kurumsal due diligence | RLS izolasyon, denetim izi | Hayır |
| 7 | Yaptırım/PEP/watchlist tarama | Ad/unvan + eşleşme sonuçları | MASAK yükümlülüğü desteği | **Self-host yente** (PII dışa çıkmaz), RLS | Hayır |
| 8 | Hassas kimlik alanları | TCKN/vergi no (E1.4'te) | Kimlik doğrulama/tekilleştirme | **AES-256-GCM** kolon şifreleme (ADR-0005) | Hayır |
| 9 | Belge/dosya saklama | Yüklenen belgeler + üretilen dosyalar | Kanıt/denetim | `retention_until` (≥{{SAKLAMA_YILI}} yıl), bütünlük hash'i | Hayır |

## C. Teknik ve İdari Tedbirler (özet)
- **Erişim:** RBAC (owner / compliance_officer / analyst / auditor); denetçi salt-okunur.
- **İzolasyon:** Kiracı-başına PostgreSQL RLS (fail-closed); uygulama süper-kullanıcı
  olmayan rolle bağlanır (ADR-0002).
- **Denetlenebilirlik:** Append-only `audit_event` + tamper-evident hash zinciri (ADR-0004).
- **Şifreleme:** İletimde TLS (E1.6); hassas kolonlarda AES-256-GCM (ADR-0005); at-rest
  disk/volume şifreleme (E1.6).
- **Sır yönetimi:** Anahtarlar/sırlar env/secrets ile; **git'e girmez** (gitleaks CI bekçi).
- **Saklama/İmha:** `retention_until` + zamanlanmış imha (dry-run önce; E3.7).
- **Yedekleme:** Gecelik yedek + ikinci konuma kopya + restore tatbikatı (E1.6).

**Sürüm:** v1 (taslak) · **Güncelleme:** {{TARIH}}
