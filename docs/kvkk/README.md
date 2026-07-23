# KVKK & Uyum Artefaktları (v1)

> ⚠️ **v1 TASLAK — hukuki inceleme gerekir.** Bu klasördeki metinler mühendislik
> tarafından, KVKK (6698 sayılı Kanun) çerçevesi ve AEGIS mimarisi esas alınarak
> hazırlanmış **taslaklardır**. Yürürlüğe koymadan önce bir KVKK uzmanı/avukat ve
> (atanmışsa) Veri Sorumlusu/İrtibat Kişisi tarafından incelenmeli, `{{...}}` yer
> tutucuları doldurulmalıdır. Bunlar hukuki tavsiye değildir.

## Roller (net ayrım)
- **AEGIS (biz):**
  - *Platform kullanıcı verisi* (ofis çalışanlarının ad/e-posta/rol'ü) bakımından **veri
    sorumlusu** → [aydınlatma-metni.md](aydinlatma-metni.md) bu veriyi kapsar.
  - *Müşterinin taradığı şirket/kişi verisi* bakımından **veri işleyen** → müşteri adına
    ve talimatıyla işler; aydınlatmayı **müşteri** (veri sorumlusu) yapar, biz
    [DPA](../legal/dpa-sablonu.md) ile destekleriz.
- **Müşteri (SMMM/YMM/denetim ofisi):** taranan gerçek/tüzel kişiler bakımından **veri
  sorumlusu** ve MASAK (5549) yükümlüsü. Karar merci müşteridir; AEGIS yalnız
  belgeler/destekler (karar-destek konumlandırması — bkz. pilot sözleşmesi).

## İçindekiler
- [aydinlatma-metni.md](aydinlatma-metni.md) — Platform kullanıcıları için aydınlatma (KVKK m.10)
- [veri-isleme-envanteri.md](veri-isleme-envanteri.md) — Kişisel veri işleme envanteri (VERBİS uyumlu)
- [verbis-kayit-hazirligi.md](verbis-kayit-hazirligi.md) — VERBİS kayıt yükümlülüğü değerlendirmesi + hazırlık
- [../legal/dpa-sablonu.md](../legal/dpa-sablonu.md) — Veri işleyen (DPA) sözleşme şablonu
- [../legal/pilot-sozlesmesi.md](../legal/pilot-sozlesmesi.md) — Pilot sözleşmesi (karar-destek sorumluluk maddesi dahil)

## Mimarinin KVKK duruşu (kod ile hizalı)
- **Veri yerelliği (Invariant 3):** Tarama self-host yente ile yapılır; müşteri PII'si
  dış tarama API'sine **çıkmaz**. Barındırma Türkiye veri merkezi seçeneklidir (E1.6) →
  yurt dışına aktarım (KVKK m.9) esasen gündeme gelmez. Faz 1'de LLM çağrısı yoktur.
- **Değiştirilemez denetim izi (Invariant 2):** Risk-etkileyen her eylem append-only
  `audit_event` + hash zinciri ile kayıt altına alınır (hesap verebilirlik).
- **Saklama (Invariant 4):** Her belge/dosya `retention_until` taşır (≥5 yıl); süre
  sonunda imha (zamanlanmış job — E3.7'de etkinleşir).
- **Şifreleme (Invariant 3):** Hassas kolonlar (TCKN/vergi no) uygulama-düzeyi AES-256-GCM
  ile şifrelenir (E1.4'te bağlanır; bkz. ADR-0005). Kiracı izolasyonu DB-düzeyi RLS ile
  (ADR-0002).
