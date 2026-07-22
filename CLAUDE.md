# AEGIS — Engineering Conventions (CLAUDE.md)

Authoritative sources: `AEGIS_Proje_Plani.docx` (product plan) and `docs/ROADMAP.md`
(delivery roadmap incl. §5 Decision Revisions). This file captures the *conventions*
that keep future work consistent. When a rule here conflicts with an epic task, the
roadmap wins — update this file in the same change.

Patterns are ported from the proven **TenderIQ** stack (FastAPI + async SQLAlchemy +
Alembic + Celery/Redis + RLS multi-tenancy + Next.js). We port *patterns*, not code
blindly.

---

## Monorepo layout

```
apps/api      aegis_api      — FastAPI (async): routers/v1, deps, middleware, errors
apps/web      @aegis/web     — Next.js 16 (App Router) + Tailwind, SSR dashboard
apps/worker   aegis_worker   — Celery workers + beat
packages/core aegis_core     — db, models, security, config, services (shared library)
packages/api-client @aegis/api-client — TS types generated from OpenAPI (contract gate)
migrations    — Alembic; 0001 = identity + RLS
infra         — compose, docker, (caddy in E1.6)
evals         — Turkish screening test set + recall-floor gate (E1.3)
scripts       — tenant-provisioning CLI, gate checks, backup/restore (E1.6)
docs          — ROADMAP.md, adr/, KVKK artifacts, pilot agreement
```

Python: **uv workspace** (`aegis-core`, `aegis-api`, `aegis-worker`). TS: **pnpm
workspace** (`@aegis/web`, `@aegis/api-client`).

## Stack pins (decided Phase 1 start)

| Component | Pin | Notes |
|---|---|---|
| Python | 3.12 · uv | |
| Next.js | 16.x | Turbopack default; **middleware renamed to `proxy.ts`** (Node runtime) |
| React | 19.2 | ships with Next 16 |
| Node | 22 LTS | Next 16 min is 20.9 |
| PostgreSQL | 16 | `gen_random_uuid()` is core (no pgcrypto needed for PKs). **No pgvector** (Revision R4) |
| Redis | 7 | |
| Elasticsearch | **9.4.2** | pinned to yente 5.5.0's own compose |
| yente | **5.5.0** | self-hosted screening; `YENTE_INDEX_URL` env var |

**yente/ES footprint (record for host sizing, E1.6):** OpenSanctions documents
**4–16 GB RAM + 10–30 GB SSD** for the ES index; yente 5.5.0 sets `ES_JAVA_OPTS=-Xms4g
-Xmx4g`. This is the dominant single-host cost — a 2–4 GB VPS will not do.

---

## Non-negotiable invariants (get right in the first migration; expensive to retrofit)

1. **Tenant isolation (RLS).** Every tenant-scoped *data* table carries `tenant_id` and
   has `ENABLE` + `FORCE ROW LEVEL SECURITY` with a `USING`/`WITH CHECK` policy against
   `current_setting('app.current_tenant', true)::uuid`. No context ⇒ `current_setting`
   returns NULL ⇒ zero rows (**fail-closed**). The app connects as the **non-superuser**
   role `aegis_app`; migrations run as the privileged `aegis` role. A cross-tenant
   isolation test (two tenants; every endpoint **and** direct SQL under `aegis_app`) runs
   in CI on every push. **Adding a tenant-scoped table = `tenant_id` + RLS policy +
   isolation assertion in the same change.** See ADR-0002.
2. **Append-only audit trail** (E1.2): `REVOKE UPDATE, DELETE` from `aegis_app` + a BEFORE
   UPDATE/DELETE trigger that RAISEs, plus a per-tenant tamper-evident **hash chain**
   (`row_hash = H(prev_hash ‖ canonical_payload)`) with a verifier. Every risk-affecting
   action (screening run, match confirm/dismiss, report export, entity edit) emits exactly
   one event with a source reference.
3. **Data locality (KVKK).** Customer PII never leaves the environment: screening is the
   self-hosted yente instance **only**, never an external screening API. No LLM calls in
   Phase 1.
4. **Provenance + retention.** Every finding carries a source reference; every stored
   document gets a `retention_until` clock (≥5 years).

### Identity / control-plane tables are RLS-exempt (deliberate)

`organization`, `user_account`, `membership` are the tenancy **control plane**, queried
**pre-auth** (register by slug, login by email → membership) via the *no-tenant* session.
RLS on them would make login fail-closed (no context yet ⇒ zero rows) or reject
registration (`WITH CHECK` sees NULL context). They are therefore **not** RLS-protected;
their endpoints are scoped in application code by `principal.tenant_id`. Every
tenant-scoped **data** table (starting with `tenant_setting`) *is* RLS-protected and is
the layer the isolation guarantee rests on. Rationale in ADR-0002.

---

## Sessions & tenancy (how to touch the DB)

- **API, no tenant** (`get_session`): identity/auth flows only (register, login).
- **API, tenant-scoped** (`get_tenant_session`): opens a transaction and calls
  `set_tenant_context` → `SELECT set_config('app.current_tenant', <uuid>, true)`
  (transaction-local, so pooled connections can't leak tenants). Use for all tenant data.
- **Worker** (`tenant_session(tenant_id)`): sync equivalent for Celery.
- JWT carries `sub` (user id), `tenant_id`, `role`. RBAC via `require_role(...)`.

## RBAC roles (AEGIS)

`owner` · `compliance_officer` · `analyst` · `auditor` (read-only). Register creates the
org's first user as **owner**. `auditor` never mutates (read-only, incl. the audit-trail
viewer in E1.5).

## Migrations

- Alembic runs **synchronously** under `DATABASE_ADMIN_URL` (privileged) — see
  `migrations/env.py`. App runtime is async under `DATABASE_URL` (`aegis_app`, RLS).
- Naming convention enforced via `Base.metadata` (`ix_/uq_/ck_/fk_/pk_`).
- Every migration that adds a tenant-scoped table must add its RLS policy in the same file.

## Turkish identifier handling (screening, E1.3 — noted now so it's consistent)

Turkish normalization (İ/ı-correct casefolding, transliteration, legal-form suffix
stripping: `A.Ş.`, `Ltd. Şti.`, `San. ve Tic.`) is a shared, heavily unit-tested module
built against the Phase-0-style test set. A **recall floor (~100% on known sanctioned
entities)** gates "screening done" in CI — false negatives are the dangerous error.
Ruff `RUF001-003` (ambiguous-unicode) are intentionally **off**: project language is
Turkish.

## Web (Next.js 16)

- Auth gate lives in **`proxy.ts`** (renamed from `middleware.ts` in Next 16; runs on the
  Node runtime, can only rewrite/redirect/modify headers). It only checks the session
  cookie for UX redirects — **real authz is backend JWT** on every API call.
- Token is stored in an **httpOnly cookie**; the browser never sees it. API calls go
  through the same-origin `/api/v1/*` proxy route, which attaches `Authorization`.
- **No hardcoded branding** (Revision R7): colors/spacing/typography via CSS variables
  (design tokens) in `globals.css`. No white-label (custom domains/sub-tenants) this phase.

## Dev workflow

```
uv sync                          # Python deps
pnpm install                     # JS deps
uv run alembic upgrade head      # migrate (needs DATABASE_ADMIN_URL)
pnpm run api:dev                 # FastAPI (uvicorn --reload)
pnpm run worker:dev              # Celery worker + beat
pnpm run web:dev                 # Next.js
docker compose -f infra/compose/docker-compose.yml up -d   # full stack

uv run ruff check . && uv run ruff format --check .        # lint
uv run mypy -p aegis_core -p aegis_api -p aegis_worker      # types (strict)
uv run pytest                    # unit tests
uv run pytest -m integration     # cross-tenant isolation gate (needs Docker)
```

## Scope discipline (Phase 1 only)

Do **not** build Phase 2+ features (UBO graph, ŞİB draft, weighted risk score, adverse
media, monitoring, billing, public API, white-label, pgvector/embeddings, LangGraph/LLM,
Apache AGE, Kubernetes). If a Phase 1 task tempts toward one, stop and note it for later.

## Epic status

- [~] **E1.1** Platform skeleton — *in progress* (this change)
- [ ] E1.2 Compliance foundation (audit trail + hash chain, retention, encryption, KVKK)
- [ ] E1.3 Screening service (yente + ES, Turkish normalization, recall floor)
- [ ] E1.4 Entity registry + verification (FtM schema, Docling, Sicil Gazetesi, ER v1)
- [ ] E1.5 Reports & dossier (rule-based summary, PDF+Word, audit viewer)
- [ ] E1.6 Production deploy + pilot onboarding
