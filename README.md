# SOP & Knowledge Retention Platform

A self-hosted system for governing standard operating procedures (SOPs) and
keeping institutional knowledge. Employees chat with one assistant bot. It
passes questions to department AI agents (IT, HR, Finance…) and only reaches
the departments the user's role allows.

**Status:** pre-alpha. The architecture and phased plan are in
[docs/architecture/sop-platform-plan.md](docs/architecture/sop-platform-plan.md).

## What's here today

| Path | Purpose |
|---|---|
| `docs/architecture/` | Platform architecture and roadmap |
| `scripts/llm-wiki` | Deterministic wiki helpers (lint, retract, index, schema), to be extracted into `backend/wiki_core` |
| `scripts/llm-wiki-session` | Session-capture helper (basis for knowledge-capture sessions) |
| `claude-plugin/` | Inherited llm-wiki workflow specs (ingest, compile, query, lint, librarian, refresh, retract), reused as agent prompt material |
| `tests/` | Structural tests, golden and defect wiki fixtures, promptfoo evals |

## Running the tests

```bash
./tests/test-plugin-validate.sh
./tests/test-structure.sh
./tests/test-local-cli-lint.sh
./tests/test-local-cli-retract.sh
./tests/test-local-cli-captions.sh
./tests/test-session-capture.sh
./tests/test-session-concurrency.sh
```

## Credits

Built on [llm-wiki](https://github.com/nvk/llm-wiki) by nvk (MIT), which follows
Andrej Karpathy's LLM wiki concept. See [LICENSE](LICENSE).
