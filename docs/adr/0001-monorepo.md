# ADR-0001: Monorepo (uv + pnpm workspace)

- **Durum:** Kabul edildi
- **Tarih:** 2026-07-22
- **Karar veren:** Scryne

## Bağlam
AEGIS; paylaşılan bir çekirdek kütüphane (modeller, db, güvenlik, servisler) üzerine
bir FastAPI API'si, Celery worker'ları ve bir Next.js istemcisi barındırır. Kod
paylaşımı (özellikle ORM modelleri ve kiracı/RLS yardımcıları) API ile worker arasında
zorunludur. TenderIQ'da kanıtlanan tek-repo düzeni doğrudan yeniden kullanılır.

## Karar
Tek repo, iki workspace yöneticisi:
- **Python:** `uv` workspace — `packages/core` (`aegis_core`), `apps/api` (`aegis_api`),
  `apps/worker` (`aegis_worker`). Ortak kök `pyproject.toml` lint/tip/test ayarlarını tutar.
- **TypeScript:** `pnpm` workspace — `apps/web` (`@aegis/web`).

Migration'lar kökte `migrations/` altında; `aegis_core.models` import edilerek
`Base.metadata`'dan üretilir. Tek `alembic.ini`.

## Sonuçlar
**Olumlu:** Model/RLS/güvenlik kodu API ve worker'da tek kaynaktan paylaşılır; atomik
değişiklik (şema + API + test aynı commit'te); tek CI.
**Ödünler:** Workspace araç zinciri (uv + pnpm) iki paket yöneticisi bilgisini gerektirir.

## İlgili
CLAUDE.md (Monorepo layout); Roadmap E1.1.
