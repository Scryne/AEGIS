# Architecture Decision Records (ADR)

Kısa, tarihli kararlar. Bir karar değişirse yeni ADR yazılır (eskisi "superseded"
işaretlenir), silinmez.

- [0001 — Monorepo (uv + pnpm workspace)](0001-monorepo.md)
- [0002 — Çok-kiracılılık: tenant_id + PostgreSQL RLS](0002-rls-multi-tenancy.md)
- [0003 — Yığın sürüm sabitleri (Next 16 / yente 5.5.0 / ES 9.4.2)](0003-stack-pins.md)
- [0004 — Append-only denetim izi + kiracı-başına hash zinciri](0004-append-only-audit-trail.md)
- [0005 — Hassas alan şifrelemesi: uygulama-düzeyi AES-256-GCM](0005-field-encryption.md)
- [0006 — Tarama mimarisi: anlık görüntü, eşik bandı, recall kapısı](0006-screening-architecture.md)
- [0007 — Varlık kütüğü: gözlem tabanlı provenans, öneri kuyruğu, ER v1](0007-entity-registry.md)
- [0008 — Raporlama: kural tabanlı risk özeti, dosya dışa aktarma, denetim görüntüleyici](0008-reporting-architecture.md)
- [0009 — Gerçek faydalanıcı hesabı: saf çekirdek, CTE, anlık görüntü, açık belirsizlik](0009-ubo-computation.md)
- [0010 — Açıklanabilir risk puanı: sabit ağırlıklı faktör modeli, kayda geçen zaman çizelgesi](0010-explainable-risk-score.md)
- [0011 — ŞİB taslağı — rehbere bağlı form, yargı alanları boş, gizlilik ve şifreli saklama](0011-sib-taslagi.md)
- [0012 — Plan ve kota — elle yetkilendirme, kayıttan sayım, özne başına sorgu](0012-plan-kota-elle-yetkilendirme.md)
- [0013 — Olumsuz haber betası — toplama + elle ayıklama, puan dışı](0013-olumsuz-haber-betasi.md)
- [0014 — Tam izleme çekirdeği ve vaka yönetimi](0014-tam-izleme-ve-vaka-yonetimi.md)
- [0015 — Toplu tarama — CSV, kütük çözümlemesi, parça parça sürdürülebilir işleme](0015-toplu-tarama.md)
