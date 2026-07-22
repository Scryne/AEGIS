# AEGIS

Multi-tenant B2B SaaS for **KYB / corporate due diligence** in the Turkish MASAK market:
verify a company's identity, screen it and its people against sanctions/PEP/watchlists via
a **self-hosted OpenSanctions yente** instance, and export an audit-proof, source-linked
dossier. AEGIS **documents and supports** the compliance decision; it never makes it.

> Status: **Phase 1 (Core MVP)** in progress — see `docs/ROADMAP.md`. Conventions and
> invariants live in `CLAUDE.md`.

## Architecture (Phase 1)

- **API** — FastAPI (async), JWT auth, tenant-resolution, RBAC, OpenAPI
- **Web** — Next.js 16 (App Router) + TypeScript + Tailwind
- **Workers** — Celery + Redis (screening, daily sync, document extraction)
- **Screening** — self-hosted yente 5.5.0 + Elasticsearch 9.4.2 (PII never leaves the env)
- **Data** — PostgreSQL 16 (pooled multi-tenancy via `tenant_id` + **RLS**), Redis, MinIO/S3
- **Deploy** — single-host Docker Compose + Caddy (E1.6); GitHub Actions CI/CD

## Quick start (dev)

```bash
cp .env.example .env            # fill AUTH_SECRET etc.
uv sync                         # Python deps (uv workspace)
pnpm install                    # JS deps (pnpm workspace)

# Bring up Postgres + Redis (+ MinIO), then migrate and run:
docker compose -f infra/compose/docker-compose.yml up -d postgres redis
uv run alembic upgrade head
pnpm run api:dev                # http://localhost:8000  (/docs for OpenAPI)
pnpm run web:dev                # http://localhost:3000
```

Screening services (heavy) are behind a compose profile:
`docker compose -f infra/compose/docker-compose.yml --profile screening up -d`.

## Tests

```bash
uv run pytest                   # unit
uv run pytest -m integration    # cross-tenant isolation gate (Docker required)
```

## Non-negotiables

Tenant RLS from migration 0001 · append-only audit trail with a tamper-evident hash chain ·
PII never sent to external screening APIs · every finding carries a source reference. See
`CLAUDE.md`.
