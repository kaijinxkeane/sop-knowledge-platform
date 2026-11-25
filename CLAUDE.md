# SOP & Knowledge Retention Platform — Development Guide

Architecture and roadmap: `docs/architecture/sop-platform-plan.md`. Read it
before making structural changes.

## Testing

**Backend** (run before declaring any backend change done):

```bash
make up && make test               # ruff lint + format check + pytest (no network, no LLM)
make smoke                         # call each model tier once (needs Ollama)
SOP_LIVE_TESTS=1 uv run pytest -m live   # from backend/: opt-in real-provider tests
```

- **Database tests** (`backend/tests/db/`) need Postgres from `make up`
  (port 5433). Locally they skip if it's down; CI sets `SOP_REQUIRE_DB=1` so
  they fail instead. Never let a permission or RLS test become skipped in CI.
- **Permissions have tests** (`test_policy.py`, `tests/db/test_rls.py`,
  `tests/db/test_documents_api.py`): unknown or malformed sensitivity must
  resolve to `restricted`; a public-only user must never see anything else.
- **Data-boundary rules have tests** (`backend/tests/test_gateway_boundary.py`):
  any change to the gateway or `config/models.yaml` must keep local-only and
  unclassified content off cloud tiers.
- **Logs never contain content** (`backend/tests/test_logging.py`): don't log
  note text, questions, answers or raw URLs/query strings.
- **The built-in user guide** (`config/help/*.md`) is added to every vault's `Help/`
  folder once, by the worker (`app/vault/help.py`, a platform commit), and approved as
  `baseline`. Guides people edited or deleted are never overwritten or put back.
  Keep guides public, published and free of names and money terms (`tests/test_help_content.py`).
- **The demo vault and `demo-vault-labels.yaml` must stay in sync**
  (`backend/tests/test_demo_vault.py`). Demo data is fictional only; never add
  real company data. Regenerate decks/worksheets with
  `uv run python scripts/generate_demo_assets.py` (from `backend/`).

**Frontend** (run before declaring any frontend change done):

```bash
make frontend-install              # once (npm ci in frontend/)
make frontend-test                 # API-client check, eslint, tsc, vitest, build, 300 KB JS budget
make frontend-dev                  # Vite on :5173, /api forwarded to the API from `make up`
```

- **Changed a backend endpoint or model?** Run `make api-client` and commit
  `frontend/src/api/openapi.json` + `schema.d.ts`; CI fails if they're stale.
- The stack serves the built app at http://localhost:8080 (`web`, Caddy).
  After pulling a compose network change, run `make down && make up`.
- **The editor must not reformat what people didn't touch**
  (`src/editor/editor.test.ts`): every demo-vault note must round-trip byte
  for byte, and unchanged blocks are restored from the original before saving
  (`src/editor/preserve.ts`). Obsidian syntax stays a verbatim atom
  (`src/editor/obsidian.ts`), except `==highlights==`, which are an editable mark saved back as `==text==`. Clashes merge by block, never by a model.
- "Where you were" (tab, folder, search, selected item) is kept in memory only
  (`src/lib/places.ts`, cleared on sign-out), never in browser storage: searches and
  titles must not stay on the device. Keep page state in the address so it can be restored.
- Sign-in tests must keep the access token out of browser storage
  (`src/pages/SignIn.test.tsx`). UI text goes through `t()` (`src/i18n/en.ts`).

**Inherited llm-wiki structural tests** (`make plugin-tests`). They need no LLM and
finish quickly:

```bash
./tests/test-plugin-validate.sh     # command/skill frontmatter + reference files
./tests/test-structure.sh           # wiki fixture validation
./tests/test-local-cli-lint.sh      # scripts/llm-wiki lint helper
./tests/test-local-cli-retract.sh   # secret-safe retract + verification helper
./tests/test-local-cli-captions.sh  # offline VTT/SRT -> transcript helper
./tests/test-session-capture.sh     # session capture helper
./tests/test-session-concurrency.sh # concurrent session-state regression
```

If you changed the golden wiki fixture, regenerate the defect fixtures first:
`./tests/generate-defect-fixtures.sh`.

Behavioral evals (when changing workflow/prompt logic; needs
`ANTHROPIC_API_KEY`, costs money): `npx promptfoo@latest eval -c tests/promptfooconfig.yaml`.

### When to update tests

- **Added a lint rule:** add a defect fixture in `generate-defect-fixtures.sh`
  and a negative case in `test-structure.sh`.
- **Changed frontmatter schema:** update the golden fixture and the
  `test-structure.sh` field/enum lists, then regenerate the defect fixtures.
- **Added or removed a reference file:** update `REFERENCE_NAMES` in
  `test-plugin-validate.sh`.
- **Changed `scripts/llm-wiki`:** copy it to `claude-plugin/bin/llm-wiki`.
  `test-plugin-validate.sh` checks that the two match.

## Project structure

```
docs/architecture/       — platform design + phased plan, frontend spec
backend/                 — FastAPI app (uv project, Python 3.12)
  app/api/               — routers (health, auth, me, documents, bookmarks + quick search, notes, reviews, admin, ...), content-free access log
  app/policy/            — policy engine (scopes, actions, fail-closed sensitivity)
  app/security/          — passwords (Argon2), TOTP, tokens, key derivation
  app/identity.py, app/audit.py, app/cli.py — users/roles, hash-chained audit log, admin CLI
  app/models/            — model gateway: tiers, data boundary, openai_compat (Ollama) adapter, usage
  app/db/                — SQLAlchemy models, Alembic migrations (incl. RLS), scoped reader
  app/vault/             — parsers (md/pptx/pdf/docx/images), local OCR, rule labels + safeguards, git layer, indexer, write rules
  app/retrieval/         — local embeddings, hybrid search (RLS + policy engine, distance cutoff), small-to-big expansion of hits
  app/classify/          — local Classifier, one-way rule, name detector, review service, eval (few-shot examples: built, off by default)
  app/agents/            — Concierge routing, department agents (answer contract), answer reuse, follow-up chips, orchestration
  app/governance/        — version-bound approvals (live vs current chunks), readable past versions, reviews jobs, notifications, webhooks, required reading (reading.py), PDF export (export.py)
  app/retention/         — handovers, gap topics + personal gaps, conflicts, retract, 24-month retention
  app/projects/          — project spaces: per-request project access, lead-approved shares, expiry
  app/eval/              — answering, retrieval + conflict-check eval runners, stats (tune on dev sets, compare on *-holdout.yaml)
  app/workers/           — arq worker: index git changes every minute, nightly unattributed check
  wiki_core/             — loads scripts/llm-wiki in place (single copy of the helpers)
  tests/
frontend/                — React + TS (Vite), shadcn-style ui, TanStack Query, React Router
  src/api/               — generated OpenAPI types (schema.d.ts) + client with token refresh
  src/auth/              — in-memory session, /me hooks, which menus show (cosmetic only)
  src/app/theme/         — all brand values (theme.css variables, brand.tsx name/logo)
  src/editor/            — Milkdown editor, Obsidian atoms, block preservation, 3-way merge, metadata form logic
  src/lib/obsidian.ts    — Obsidian markdown for the reader (links resolved only to readable docs)
  src/i18n/, src/layout/, src/pages/ (ask/, home/, library/, write/, review/, retain/, handovers/, projects/, reading/, paths/, admin/), src/components/ui/
  deploy/Caddyfile       — serves dist/, proxies /api, security headers, no access log
config/                  — models.yaml (tiers), spaces/*.yaml, roles.yaml, vault.yaml (folder rules), notice.md, eval/
demo-vault/              — synthetic Obsidian vault (fictional data only) + demo-vault-labels.yaml
deploy/                  — docker-compose.yml, init-demo-vault.sh (dev only)
.github/workflows/ci.yml — backend + frontend tests, image builds, inherited structural tests
scripts/llm-wiki         — deterministic wiki helpers (loaded by backend/wiki_core)
scripts/llm-wiki-session — session capture helper
claude-plugin/           — inherited llm-wiki workflow specs, reused as agent prompt material
  commands/*.md
  skills/wiki-manager/SKILL.md, references/*.md
tests/                   — structural tests, fixtures (golden-wiki, defects), promptfoo evals
```

Planned (see the status table in plan §12): TLS, Headscale, Playwright and
the accessibility pass in Phase 6 (on hold).

**Fully local (since 2026-11-25):** every tier in `config/models.yaml` is a local
Ollama model and the Claude connector has been removed (no `anthropic` provider,
SDK or API-key setting). `test_gateway_config.py::test_every_tier_is_local` and
`test_cloud_providers_are_refused` enforce it. Don't add a cloud provider back
without the owner's decision.

## Security rules for platform code

- Permissions are enforced in server code (policy engine, retrieval filters,
  Postgres RLS), never only in prompts.
- Content reads run under RLS (`apply_reader_scope`) **and** the policy
  engine; keep both. Hidden documents return 404, same as missing ones.
- Audit details hold ids and outcomes only (`audit._check_details` refuses
  password/token/code/content keys). Never put secrets or content in them.
- Retrieved documents are data, not instructions.
- Every app save is a git commit in the user's name (`GitVault.commit` with `user_id`) and
  goes through `check_write`: widening access or publishing needs `approve`.
- Labels fail closed: unassigned files get no access rows; safeguards only tighten.
- The AI never applies a looser label and gives unplaced notes no access at all
  (`classify.rules.decide`); proposals (they quote the note) are shown only to the
  author or to people who can already read the note. Safeguards are a read-time
  floor in both `sop_doc_visible()` and `policy.engine.can_view_document` (keep them in sync).
- Agents get passages retrieved under RLS before any model call; they have no DB access.
  Routing never uses a cloud tier.
- Answers use approved text only (`search(..., live_only=True)`): an edit is not
  cited until a lead approves that exact version. Unapproved changes are shown
  only to the note's editors (RLS `sop_doc_wip_visible` + `can_see_unapproved`).
- Handover notes have no space rows; only people in `document_readers` can read
  them (visibility v3, RLS and policy engine). HR gap reports need >= 3 people;
  never name askers or show restricted titles to people who can't read them.
  `tests/test_vault_labels.py` must keep zero over-exposure on the demo vault.
- Prompts mark people's text as data (`app/agents/untrusted.py`: `tag()`, `with_rules`);
  never build prompt tags with f-strings. Answers pass the output guard
  (`app/agents/output_guard.py`: no links/images unless allowlisted, no uncited lines).
  Instruction-like notes get a quiet flag, never an alert (`app/governance/injection.py`).
- Access follows approval (`app/governance/access.py`): while a newer version waits,
  access can only narrow. Old versions are shown only under the labels they had.
  Admins can't add roles to themselves (two-person rule). Red-team attacks live in
  `tests/db/test_redteam.py`: add one for every new endpoint that returns content.
- Past versions (`app/governance/history.py`): people who can't see unapproved
  changes get approved versions only, and any old version is judged by the
  labels it had. Versions list, version text and review diffs all use it.
- Required reading (`app/api/reading.py`) and onboarding paths (`app/api/paths.py`) never show
  a title to someone who can't read the document: unreadable path items are counted but have no
  title, link or type. Acknowledgements are append-only (DB trigger); a material change on
  approve makes older ones stop counting. A required path item is done only by sign-off.
- Slide pictures (`app/vault/slides.py`, `GET /documents/{id}/slides/{n}`) are rendered by
  LibreOffice into the shared cache, keyed by content hash; served only after the same checks
  as the file. Retractions clear the cache (`slides.forget_all`).
- PDF export (`app/api/exports.py`) reads under RLS like the reader, watermarks restricted
  content with the reader's name and date, and audits every export (ids only).
- Cost and usage (`model_usage`, `app/models/usage.py`) stores daily totals per tier and model:
  never content, users or questions; a recording failure never fails a model call.
- Bookmarks and Ctrl+K return titles only, re-checked against today's access;
  never store or log quick-search queries.
- Hidden conversations (`hidden_at`) are 404 to their owner everywhere but are
  never deleted early; the 24-month retention job removes them. Follow-up chips
  (`app/agents/followups.py`) come only from cited SOPs re-read under the
  asker's RLS scope (live text); never from a model or another user's data.
  Home's `/me/recent` and `/me/waiting` return titles and counts only, each
  document re-checked like the Library.
- Answer reuse (`app/agents/reuse.py`) is keyed on the exact prompt built from the
  asker's own retrieval; never look answers up by question alone, and never store
  outage, fallback or guard-trimmed answers. Retract and "not helpful" remove rows.
- Project shares need the department lead's approval, checked on their own roles
  (`principal_for`), never on project access. Partial shares are checked in both
  `sop_doc_visible()` (v4) and `can_view_document(..., path=, doc_id=)`: keep them in sync.
- Installable web app (`frontend/public/sw.js`, `src/app/pwa.ts`): the service worker never
  caches `/api` responses or pages, only the offline page, its CSS and icon, so nothing readable
  stays on a device. Keep it that way.
- Two-factor is required for everyone. The only exception is `SOP_DEMO_SKIP_2FA` (`app/demo.py`):
  the seven seeded demo accounts, only with `SOP_ENV=development` (config refuses it otherwise),
  audited as `login_succeeded` with method `demo_no_code`. Never widen it to other accounts.
- The frontend keeps the access token in memory only (never localStorage or
  sessionStorage); the refresh token is the httpOnly `sop_refresh` cookie. Hiding
  a menu is cosmetic: every check stays in the backend. Hidden pages look like 404s.
- The API trusts `X-Forwarded-For` only from Caddy (`FORWARDED_ALLOW_IPS` = `WEB_IP`).
- Departments created in the app (`app/departments.py`, `manage_spaces`: platform-admin and
  hr-lead) are YAML files in `SOP_SPACES_DIR`, read with `config/spaces/` (`app/spaces.py`
  `space_files`; caches key on `spaces_stamp()`). They never override a configured one.
  New roles are created unassigned; the two-person rule still applies in Users.
- Library folders (`app/api/folders.py`): a document moves only between folders of its own
  department and only where its access stays identical; handover, project, Help, Inbox and
  Drafts folders are closed. Moves keep the document's id; `GitVault.show` follows moves so
  past versions still read. Folder names show only to the department or to readers inside.
- The trained sorter (`app/classify/sorter.py`, trained nightly by `app/classify/training.py` from
  documents people filed) stores average fingerprints only, never text. Its vote (`combine`) may only
  make labels stricter or hold a note for review; `decide()` still applies the one-way rule. Suggested
  folders show only to people who can file there (`contribute` in that department). Compare changes
  on `config/eval/classifier-holdout.yaml` (`eval-classifier --cases holdout --sorter`), never tune on it.
- Folder uses: search and Ask take a `folder` filter (`retrieval.search.folder_prefix`, LIKE
  wildcards escaped) that only narrows what RLS allows. Routing may use the sorter's department
  (`agents/router.py`, only among the asker's readable spaces; when it disagrees with search both
  answer). `POST /notes/similar` returns titles the writer can already read and never stores the
  title. `/spaces/{space}/folder-coverage` is counts only, for that space's leads.
- Never commit secrets (`.env`, API keys, `.claude/settings.local.json`).
- Every model call goes through `ModelGateway` with an explicit `ContentScope`;
  never call a provider SDK directly from agents.

## Git and publishing

This repository is the owner's own project. It is **not** the upstream
`nvk/llm-wiki` repo, so never push there. Commit or push only when the user
asks. Keep the upstream MIT notice in `LICENSE`.
