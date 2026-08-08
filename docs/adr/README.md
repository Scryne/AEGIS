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
