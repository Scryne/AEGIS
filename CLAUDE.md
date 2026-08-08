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
migrations    — Alembic; 0001 = identity + RLS … 0005 = report
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
| Reporting | jinja2 · xhtml2pdf · python-docx | pure Python, **no native deps** (ADR-0008) |

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

## Turkish identifier handling (screening, E1.3 — implemented)

Turkish normalization lives in `aegis_core.screening.normalization` and is the single
module both the **query** and the **dataset** side pass through. İ/ı-correct casefolding
(Python's `str.lower()` gets this wrong), ASCII transliteration, legal-form suffix
stripping (`A.Ş.`, `Ltd. Şti.`, `San. ve Tic.`) including mid-name forms
(`… A.Ş. İstanbul Şubesi`). **Suffix tables are matched ASCII-folded** so `Ltd. Şti.`
and `LTD STI` need one entry, not two.

A **recall floor of 100%** gates screening in CI, in two layers (see `evals/README.md`):

1. `evals/test_normalization_recall.py` — every spelling variant of the same entity must
   reach the same canonical key. Runs on every push, no Docker.
2. `evals/test_screening_recall.py` — real yente + Elasticsearch over a 34-entity fixture
   dataset (`-m screening`, own CI job). Variants are **not** indexed; only reference
   spellings are, so the test can't validate itself.

`distinct_pairs` in the case file guards the other direction: over-stripping must not
collapse different entities. Ruff `RUF001-003` (ambiguous-unicode) are intentionally
**off**: project language is Turkish.

## Entity registry invariants (E1.4 — see ADR-0007)

- **Every value is an observation.** `entity` holds the currently-accepted value;
  `entity_attribute` holds each observation with its source and timestamp. Data from
  documents/registries is recorded with `promote_to_current=False` — it never silently
  overwrites the customer's declaration; a conflict becomes a `discrepancy`.
- **Discrepancies are decided, not closed.** A reason is mandatory (MASAK audit asks
  "why was this accepted"); the record stays for the dossier.
- **Extraction never writes to the registry.** Docling output becomes
  `extraction_proposal` rows awaiting human confirmation (R2). Rejected proposals persist.
- **Identifier checksums are advisory.** A number that fails its check digit is still
  saved, with a warning — refusing to record what the customer's document says is not
  acceptable. The same checks are used *strictly* as a precision filter during extraction.
- **TCKN is encrypted** (`EncryptedString`) with a keyed `blind_index` for equality
  search. Attribute rows, discrepancies, proposal evidence and audit payloads carry only
  the **masked** form. Tax/MERSİS/LEI stay plain — public company identifiers that ER
  matches on.
- **ER never auto-merges.** Deterministic identifier → conflict guard (similar name but
  different tax number is *not* a match) → `pg_trgm` fuzzy → ambiguity goes to a human.
  Merging marks the source `merged`; it never deletes.
- **Docling is an optional install** (`uv sync --group extraction`, worker image only).
  Not installed ⇒ document is stored and marked `skipped`; upload still succeeds.

## Reporting invariants (E1.5 — see ADR-0008)

- **Risk level is a rule, not a score.** `reports/risk.py` runs transparent rules
  (confirmed sanctions → High, confirmed PEP → Elevated, open critical discrepancy →
  Elevated) and the level is the **maximum** of the findings — no hidden weighting. Every
  finding carries a plain-Turkish `rationale` that is printed in the report. A weighted /
  learned score is Phase 2.
- **An undecided match never raises the level.** A high-scoring but unconfirmed candidate
  carries `level=None`: it does not touch the level, it sets `complete=False`. Anything
  else would breach "no auto-confirm" (ADR-0006) through the back door.
- **"No result" ≠ "clean".** No screening or a failed run ⇒ `unknown` (Belirsiz), never
  `standard`. Ranking is `standard < unknown < elevated < high`.
- **What counts as a sanctions/PEP hit lives in `screening/topics.py`** — the on-screen
  counter and the risk rule must never disagree.
- **Dismissed matches stay in the dossier**, with their band and reason. So do the run's
  frozen thresholds and dataset versions: the report answers "against which list, at
  which threshold" on its own.
- **PDF = Jinja2 → xhtml2pdf/reportlab** (pure Python; WeasyPrint's Pango dependency was
  rejected — R6). Turkish glyphs need reportlab's bundled **Bitstream Vera** TTF faces,
  registered directly (xhtml2pdf's `@font-face` path breaks on Windows). Tests read the
  text back out of the produced PDF.
- **PDF and Word are rendered from one `DossierData`**, so they cannot drift. TCKN is
  **masked** in reports; tax/MERSİS/LEI print in full.
- **Exported files freeze.** Written to object storage first, then the `report` row with
  `sha256` + `retention_until`; storage failure ⇒ no row. Exactly one `report.export`
  audit event, `source_ref = sha256:…`. The **live** risk summary writes no event.
- **Audit viewer is read-only**, ordered by `seq` (not `occurred_at`), open to
  owner/compliance_officer/auditor — analyst excluded.

## Screening invariants (E1.3 — see ADR-0006)

- **No auto-confirm.** A high score flags a candidate; it never confirms it. Confirmation
  is a human decision (decision *support*, not decision).
- **No candidate is deleted.** Auto-dismissed matches persist with their reason — the
  dossier (E1.5) must show "matches dismissed, with reason".
- **A failed run is never "clean".** yente unreachable ⇒ screening persists as `failed`,
  audit event written, API returns 502, UI says "screening could not run — no result".
  Stale data (>24h) warns in the UI and alerts via Sentry from `sanctions.sync`.
- **Provenance frozen at run time:** dataset versions + thresholds are written onto the
  `screening` row, so later threshold changes never reinterpret an old run.
- **Identifiers (TCKN/vergi no) are stored masked** until E1.4 puts them in
  `EncryptedString` columns on `entity`.

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
uv run pytest                    # unit tests + normalization recall gate
uv run pytest -m integration     # cross-tenant isolation gate (needs Docker)

# End-to-end screening recall gate (yente + Elasticsearch, ~1GB heap)
uv run python evals/build_eval_dataset.py
docker compose -f infra/compose/docker-compose.evals.yml up -d --wait
YENTE_TEST_URL=http://localhost:8002 uv run pytest -m screening
docker compose -f infra/compose/docker-compose.evals.yml down -v

# Screening stack for local dev (heavy: ES 4GB heap)
docker compose -f infra/compose/docker-compose.yml --profile screening up -d
```

## Scope discipline (Phase 1 only)

Do **not** build Phase 2+ features (UBO graph, ŞİB draft, weighted risk score, adverse
media, monitoring, billing, public API, white-label, pgvector/embeddings, LangGraph/LLM,
Apache AGE, Kubernetes). If a Phase 1 task tempts toward one, stop and note it for later.

## Epic status

- [x] **E1.1** Platform skeleton — RLS multi-tenancy, auth, CI, cross-tenant isolation gate
- [~] **E1.2** Compliance foundation — *core complete; ops-bound items deferred*
  - [x] Append-only `audit_event` (REVOKE + BEFORE trigger) + per-tenant hash chain +
    `verify_chain` verifier + `/audit/verify`; wired into settings mutation (ADR-0004)
  - [x] Retention scaffolding: `RetentionMixin` + `document_retention_years` + daily
    disposal job **stub** (dry-run; real deletion activates E3.7)
  - [x] Field encryption: app-level AES-256-GCM (`SecretBox`/`EncryptedString`) instead of
    pgcrypto (ADR-0005); `FIELD_ENCRYPTION_KEY` prod fail-fast. Mechanism ready; applied to
    national-ID columns in E1.4
  - [x] KVKK artifacts v1 (`docs/kvkk/`: aydınlatma metni, processing inventory, VERBİS
    prep) + DPA + pilot agreement with decision-support liability clause (`docs/legal/`)
  - [ ] *Deferred to E1.6 (ops/deploy):* TLS everywhere, at-rest encrypted volumes,
    secrets via SOPS/age or Docker secrets, VERBİS filing (legal review + fill placeholders)
- [~] **E1.3** Screening service — *core complete; two items need live verification*
  - [x] Turkish normalization module + 34-case eval set + **100% recall floor in CI**
    (two layers: normalization on every push, end-to-end vs. real yente in its own job)
  - [x] yente client (async API + sync worker), defensive response parsing
  - [x] Migration 0003: `screening` + `match_candidate` (RLS, in the isolation gate) +
    `sanctions_dataset` (RLS-exempt, see ADR-0006)
  - [x] `POST /screenings` sync path + `POST /screenings/deep` (Celery) + HITL review
    endpoints; every run/decision emits one audit event
  - [x] Per-tenant threshold band (`screening.thresholds` setting) — auto-dismiss /
    review / auto-flag, **no auto-confirm**
  - [x] Daily `sanctions.sync` beat job: MASAK rebuild → yente reindex → freshness metric
    → staleness alert (Sentry + `GET /screenings/datasets`)
  - [x] MASAK freeze-list → FtM converter + yente manifest + operator CLI
    (`scripts/masak_dataset.py`)
  - [x] Screening UI: run form, results with score + "why matched" features, review
    actions, stale-data and failed-run warnings
  - [x] Verified against real yente 5.5.0 + ES 9.4.2: manifest `entities_url: file://`
    loads, end-to-end recall gate green (36/36). **`YENTE_AUTO_REINDEX` must be `true`** —
    when false, yente skips even the *first* index and `/readyz` stays 503 forever.
  - [ ] *Needs live verification before pilots:* (a) MASAK source file column layout
    against `COLUMN_ALIASES`, (b) manifest `datasets:` collection (`aegis_all`) together
    with the OpenSanctions catalog, (c) the `/updatez` contract — each isolated to one
    file, and (b)/(c) are non-blocking (the sync job warns rather than fails)
- [~] **E1.4** Entity registry + verification — *core complete; PDF path needs pilot docs*
  - [x] FtM-aligned `entity` / `entity_attribute` / `relationship` + **provenance as
    observations** (every value carries source + timestamp; ADR-0007)
  - [x] Company/person CRUD with Turkish identifier checks (TCKN · VKN · MERSİS · LEI) —
    **advisory, never blocking**; TCKN encrypted (`EncryptedString`) + blind index
    (closes E1.2's deferred "apply field encryption to national-ID columns")
  - [x] Document upload → MinIO → Turkish extraction (imza sirküleri / faaliyet belgesi /
    gazette) → `extraction_proposal` requiring **human confirmation** (R2)
  - [x] Discrepancy flagging: declared vs. document/registry, severity-ranked, decided
    with a mandatory reason (never silently closed)
  - [x] ER v1 (R4): deterministic identifiers → **conflict guard** → `pg_trgm` fuzzy →
    merge-or-create, ambiguity goes to a human; merge preserves the source record
  - [x] GLEIF enrichment sending **only the LEI** outward, audited, never overwriting
    the declaration
  - [x] Ticaret Sicil Gazetesi as guided manual attach with source reference (R1 — no
    automated lookup until E0.3 produces a verdict)
  - [x] `POST /screenings/from-entity/{id}` — screens the company **with its officers/UBOs**
    from the registry (E1.3 × E1.4)
  - [ ] *Needs verification with real files:* Docling PDF path (optional `extraction`
    dependency group; the plain-text path is covered end-to-end in tests), and the VKN
    checksum against the official specification
- [x] **E1.5** Reports & dossier — *complete*
  - [x] Rule-based risk summary v1 (`reports/risk.py`), transparent + plain-Turkish
    rationale per finding; shared sanctions/PEP predicate in `screening/topics.py`
  - [x] Migration 0005: `report` (RLS, in the isolation gate) with `sha256` integrity
    proof + `retention_until`; risk verdict and dataset versions frozen at export
  - [x] Dossier export PDF (Jinja2 → xhtml2pdf) + Word (python-docx) from one
    `DossierData`; dismissed-with-reason matches, discrepancies, source refs, run
    timestamps + dataset versions; TCKN masked (ADR-0008)
  - [x] `POST /reports/dossier` · `GET /reports[/{id}][/download]` ·
    `GET /reports/risk/{entity_id}` (live, writes no audit event); auditor reads but
    cannot export
  - [x] Audit-trail viewer: `GET /audit/events` (paginated + filters, `seq`-ordered) and
    the `/audit` page with a chain-verification badge; analyst excluded
  - [x] Web: risk panel + export buttons + generated-reports list on the entity page
- [ ] E1.6 Production deploy + pilot onboarding
