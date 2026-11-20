# Common development commands. Run from the repository root.
COMPOSE := docker compose --env-file .env -f deploy/docker-compose.yml

.PHONY: help env demo-vault up down logs ps test lint smoke smoke-docker plugin-tests

help:
	@echo "make env          create .env from .env.example (then add your API key)"
	@echo "make demo-vault   create the development vault repo from demo-vault/ (fictional data)"
	@echo "make up / down    start / stop the stack (postgres, redis, api, worker)"
	@echo "make test         backend unit tests + lint"
	@echo "make smoke        call every model tier once (Claude + local Ollama)"
	@echo "make plugin-tests inherited llm-wiki structural tests"

env:
	@test -f .env && echo ".env already exists" || (cp .env.example .env && echo "created .env")

demo-vault:
	./deploy/init-demo-vault.sh

up: env
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

test:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q

smoke:
	cd backend && uv run python -m app.models.smoke $(ARGS)

smoke-docker:
	$(COMPOSE) exec api python -m app.models.smoke $(ARGS)

plugin-tests:
	@for t in tests/test-plugin-validate.sh tests/test-structure.sh tests/test-local-cli-lint.sh \
	  tests/test-local-cli-retract.sh tests/test-local-cli-captions.sh tests/test-session-capture.sh \
	  tests/test-session-concurrency.sh; do bash $$t >/dev/null 2>&1 && echo "PASS $$t" || { echo "FAIL $$t"; exit 1; }; done
