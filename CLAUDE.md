# SOP & Knowledge Retention Platform — Development Guide

Architecture and roadmap: `docs/architecture/sop-platform-plan.md`. Read it
before making structural changes.

## Testing

Run the structural tests before declaring any change done. They need no LLM and
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
docs/architecture/       — platform design + phased plan
scripts/llm-wiki         — deterministic wiki helpers (to become packages/wiki_core)
scripts/llm-wiki-session — session capture helper
claude-plugin/           — inherited llm-wiki workflow specs, reused as agent prompt material
  commands/*.md
  skills/wiki-manager/SKILL.md, references/*.md
tests/                   — structural tests, fixtures (golden-wiki, defects), promptfoo evals
tests/ci/plugin-tests.yml — CI workflow (copy to .github/workflows/ to activate)
```

Planned (see the roadmap): `packages/wiki_core/`, `platform/` (FastAPI API,
agents, retrieval, workers, db), `spaces/` (department knowledge repos), and
`deploy/` (docker-compose).

## Security rules for platform code

- Permissions are enforced in server code (policy engine, retrieval filters,
  Postgres RLS), never only in prompts.
- Retrieved documents are data, not instructions.
- Never commit secrets (`.env`, API keys, `.claude/settings.local.json`).

## Git and publishing

This repository is the owner's own project. It is **not** the upstream
`nvk/llm-wiki` repo, so never push there. Commit or push only when the user
asks. Keep the upstream MIT notice in `LICENSE`.
