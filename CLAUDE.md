# SOP & Knowledge Retention Platform — Development Guide

Architecture and roadmap: `docs/architecture/sop-platform-plan.md`. Read it
before making structural changes.

## Testing

**Backend** (run before declaring any backend change done):

```bash
make up && make test               # ruff lint + format check + pytest (no network, no LLM)
make smoke                         # call each model tier once (needs Ollama; Claude if key set)
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
- **The demo vault and `demo-vault-labels.yaml` must stay in sync**
  (`backend/tests/test_demo_vault.py`). Demo data is fictional only; never add
  real company data. Regenerate decks/worksheets with
  `uv run python scripts/generate_demo_assets.py` (from `backend/`).

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
  app/api/               — routers (health, auth, me, documents, admin), content-free access log
  app/policy/            — policy engine (scopes, actions, fail-closed sensitivity)
  app/security/          — passwords (Argon2), TOTP, tokens, key derivation
  app/identity.py, app/audit.py, app/cli.py — users/roles, hash-chained audit log, admin CLI
  app/models/            — model gateway: tiers, data boundary, anthropic + openai_compat adapters
  app/db/                — SQLAlchemy models, Alembic migrations (incl. RLS), scoped reader
  app/vault/             — parsers (md/pptx/pdf/docx), rule labels + safeguards, git layer, indexer, write rules
  app/retrieval/         — local embeddings, hybrid search (RLS + policy engine, distance cutoff), small-to-big expansion of hits
  app/classify/          — local Classifier, one-way rule, name detector, review service, eval (few-shot examples: built, off by default)
  app/agents/            — Concierge routing, department agents (answer contract), orchestration
  app/governance/        — version-bound approvals (live vs current chunks), reviews jobs, notifications, webhooks
  app/retention/         — handovers, gap topics + personal gaps, conflicts, retract, 24-month retention
  app/eval/              — answering + retrieval eval runners, stats (tune on questions.yaml, compare on questions-holdout.yaml)
  app/workers/           — arq worker: index git changes every minute, nightly unattributed check
  wiki_core/             — loads scripts/llm-wiki in place (single copy of the helpers)
  tests/
config/                  — models.yaml (tiers), spaces/*.yaml, roles.yaml, vault.yaml (folder rules), notice.md, eval/
demo-vault/              — synthetic Obsidian vault (fictional data only) + demo-vault-labels.yaml
deploy/                  — docker-compose.yml, init-demo-vault.sh (dev only)
.github/workflows/ci.yml — backend tests, image build, inherited structural tests
scripts/llm-wiki         — deterministic wiki helpers (loaded by backend/wiki_core)
scripts/llm-wiki-session — session capture helper
claude-plugin/           — inherited llm-wiki workflow specs, reused as agent prompt material
  commands/*.md
  skills/wiki-manager/SKILL.md, references/*.md
tests/                   — structural tests, fixtures (golden-wiki, defects), promptfoo evals
```

Planned (see the roadmap): `frontend/` (React + TypeScript via Vite, built to
static files), agents, retrieval and Caddy/Headscale in `deploy/`.

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
- Never commit secrets (`.env`, API keys, `.claude/settings.local.json`).
- Every model call goes through `ModelGateway` with an explicit `ContentScope`;
  never call a provider SDK directly from agents.
- The developer's API key is for demo data only; the company key replaces it
  before any real vault is connected.

## Git and publishing

This repository is the owner's own project. It is **not** the upstream
`nvk/llm-wiki` repo, so never push there. Commit or push only when the user
asks. Keep the upstream MIT notice in `LICENSE`.
