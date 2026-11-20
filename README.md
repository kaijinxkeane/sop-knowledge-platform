# SOP & Knowledge Retention Platform

A self-hosted system for governing standard operating procedures (SOPs) and
keeping institutional knowledge. Employees chat with one assistant bot. It
passes questions to department AI agents (IT, HR, Finance…) and only reaches
the departments the user's role allows.

**Status:** pre-alpha (Phase 0: foundations). Architecture and phased plan:
[docs/architecture/sop-platform-plan.md](docs/architecture/sop-platform-plan.md);
frontend spec: [docs/architecture/frontend-spec.md](docs/architecture/frontend-spec.md).

## Quick start (development, Mac)

Needs Docker Desktop, [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com).

```bash
make env                 # creates .env; add ANTHROPIC_API_KEY for the Claude tiers
make demo-vault          # creates the dev vault repo from demo-vault/ (fictional data)
make up                  # postgres + redis + api + worker
curl -s localhost:8000/api/v1/health
ollama pull qwen3:4b && ollama pull qwen3:8b && ollama pull qwen3-embedding:0.6b   # Classifier candidates + embeddings
make smoke               # calls each model tier once
make test                # backend lint + tests
```

API docs: http://localhost:8000/api/v1/docs

## What's here today

| Path | Purpose |
|---|---|
| `docs/architecture/` | Platform architecture, roadmap, frontend spec |
| `backend/` | FastAPI API, model gateway, worker, migrations, tests |
| `config/` | Model tiers (`models.yaml`) and space settings |
| `demo-vault/` | Synthetic Obsidian vault of a fictional training company, with ground-truth labels |
| `deploy/` | Docker Compose stack and dev vault setup |
| `scripts/llm-wiki` | Deterministic wiki helpers (lint, retract, index, schema), loaded by `backend/wiki_core` |
| `scripts/llm-wiki-session` | Session-capture helper (basis for knowledge-capture sessions) |
| `claude-plugin/` | Inherited llm-wiki workflow specs (ingest, compile, query, lint, librarian, refresh, retract), reused as agent prompt material |
| `tests/` | Structural tests, golden and defect wiki fixtures, promptfoo evals |

## Running the tests

```bash
make test           # backend
make plugin-tests   # inherited llm-wiki structural tests
```

## Credits

Built on [llm-wiki](https://github.com/nvk/llm-wiki) by nvk (MIT), which follows
Andrej Karpathy's LLM wiki concept. See [LICENSE](LICENSE).
