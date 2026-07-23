# ADR-0005: Hassas alan şifrelemesi — uygulama-düzeyi AES-256-GCM (pgcrypto değil)

- **Durum:** Kabul edildi
- **Tarih:** 2026-07-23
- **Karar veren:** Scryne
- **İlgili:** CLAUDE.md Invariant 3 (veri yerelliği/KVKK); ROADMAP §7 E1.2 (encryption);
  ADR-0002 (RLS)

## Bağlam
KVKK, TCKN/vergi no gibi özel nitelikli/hassas kimlik verilerinin at-rest korunmasını
gerektirir. ROADMAP E1.2 bunu "pgcrypto for sensitive columns (national IDs)" olarak
listeler. Şifreleme mekanizması, hassas kolonlar var olmadan **önce** kilitlenmelidir:
canlı PII'ye sonradan şifreleme eklemek, RLS/audit izi gibi pahalı bir retrofit'tir.

## Karar
Hassas string kolonları **uygulama-düzeyi AES-256-GCM** ile şifrelenir (pgcrypto yerine),
`aegis_core.security.encryption` içinde:
- `SecretBox` — AES-256-GCM; token = `base64(nonce(12B) ‖ ciphertext+tag)`; her
  şifrelemede rastgele nonce; isteğe bağlı `aad` (ör. tenant_id) ile bağlama bağlama.
- `EncryptedString` — şeffaf SQLAlchemy `TypeDecorator`; DB'de ciphertext (`Text`),
  Python'da düz string. E1.4 kimlik-no kolonları bu tipi kullanacak.
- Anahtar `FIELD_ENCRYPTION_KEY` (base64, 32 bayt) ile secrets/env'den gelir; **asla
  git'e girmez** ve production'da fail-fast zorunludur (bkz. `config.py`).

**pgcrypto yerine neden uygulama-düzeyi:**
1. **Anahtar sızıntısı:** pgcrypto (`pgp_sym_encrypt(data, key)`) simetrik anahtarı SQL
   ifadesinin metnine koyar → `pg_stat_statements`, yavaş-sorgu logları ve olası hata
   izlerine düşer. Uygulama-düzeyi AEAD'de anahtar süreç belleğinde kalır, DB hiç görmez.
2. **Kimlik doğrulama:** GCM authenticated encryption'dır; kurcalanmış ciphertext çözümde
   `DecryptionError` verir (bütünlük kanıtı). pgcrypto'nun sürüm/varsayılanlarına göre bu
   garanti aynı netlikte değildir.
3. **Yerellik/bağımlılık:** DB uzantısı ve süper-kullanıcı gerekmez; tek-host solo
   duruşuyla (R6) uyumlu, test edilebilirliği yüksek (Docker'sız birim testleri).

**Ödün:** Şifreli değer deterministik değildir → üzerinde SQL ile arama/`JOIN` yapılamaz.
Eşitlik araması gereken hassas alanlar için (ör. TCKN ile tekilleştirme) E1.4'te ayrı,
aramaya-özel bir **HMAC/hash kolonu** eklenir (anahtarlı, tuzlu). Bu bilinçli kabul edilir;
Phase 1'de hassas alanlar üzerinde SQL araması bir gereksinim değildir.

## Sonuçlar
**Olumlu:** Anahtar loglara sızmaz; AEAD ile kurcalama tespiti; DB uzantısı yok; mekanizma
şimdi kilitli ve birim-testli, E1.4'te kolon eklemek bir satır (`EncryptedString`).
**Ödünler:** Anahtar yönetimi operatörün sorumluluğunda (secrets; rotasyon prosedürü E1.6
ops runbook'una girer); şifreli kolonlarda SQL arama yok (yukarıdaki hash-kolonu telafisi).

## Alternatifler
- **pgcrypto:** Yukarıdaki anahtar-sızıntısı nedeniyle reddedildi.
- **Şifrelenmemiş + yalnız disk/volume şifreleme:** At-rest tek katman; DB dökümü/yedeği
  düz PII taşırdı. Kolon şifrelemesi ek, uygulama-içi katmandır (disk şifreleme E1.6'da ayrıca).
- **KMS/zarf şifreleme (envelope):** İleride (E4 kurumsal) DEK/KEK ayrımına genişletilebilir;
  `SecretBox` arayüzü bunu engellemez. Phase 1 için tek anahtar yeterli.

## İlgili
CLAUDE.md (Invariant 3); `packages/core/src/aegis_core/security/encryption.py`;
`packages/core/tests/test_encryption.py`; `config.py` (FIELD_ENCRYPTION_KEY fail-fast).
