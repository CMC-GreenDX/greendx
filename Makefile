.DEFAULT_GOAL := help

PYTHON ?= python
PROFILE ?= core

# Local settings (copied from .env.example on first `make up`).
-include .env
export

COMPOSE := docker compose --env-file .env -f deploy/compose/docker-compose.yml --profile $(PROFILE)
HASURA_URL ?= http://localhost:8081

.PHONY: help setup lint lint-md lint-yaml lint-commits changelog up down reset ps logs health bootstrap demo

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' Makefile | awk 'BEGIN {FS = ":.*## "} {printf "  %-20s %s\n", $$1, $$2}'

.env:
	cp .env.example .env

up: .env ## Start the services of PROFILE (default: core), wait until healthy, apply metadata
	$(COMPOSE) up -d --wait
	@$(MAKE) --no-print-directory bootstrap

down: ## Stop the services and keep their data
	$(COMPOSE) down

reset: ## Stop the services and delete their data volumes
	$(COMPOSE) down --volumes

ps: ## Show service status
	$(COMPOSE) ps

logs: ## Follow service logs
	$(COMPOSE) logs -f --tail=100

health: ## Check that every core service is healthy
	@bash deploy/compose/health.sh

bootstrap: ## Apply Hasura metadata (tables and tenant permissions)
	@curl -fsS -X POST "$(HASURA_URL)/v1/metadata" \
		-H "Content-Type: application/json" \
		-H "X-Hasura-Admin-Secret: $(HASURA_ADMIN_SECRET)" \
		-d @deploy/compose/demo/hasura/metadata.json && echo " Hasura metadata applied."

demo: ## Run the scripted core demo (identity, gateway, tenant isolation)
	@bash deploy/compose/demo/demo.sh

setup: ## Install the pinned lint and changelog tooling
	npm ci
	$(PYTHON) -m pip install -r requirements-dev.txt

lint: lint-md lint-yaml ## Run all linters

lint-md: ## Lint Markdown files
	npm run lint:md

lint-yaml: ## Lint YAML files
	$(PYTHON) -m yamllint --strict .

lint-commits: ## Check commit messages on this branch against origin/main
	npm run lint:commits

changelog: ## Regenerate CHANGELOG.md from commit history
	npm run changelog
