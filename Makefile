.DEFAULT_GOAL := help

PYTHON ?= python
PROFILE ?= core

# Local settings (copied from .env.example on first `make up`).
-include .env
export

COMPOSE := docker compose --env-file .env -f deploy/compose/docker-compose.yml --profile $(PROFILE)
HASURA_URL ?= http://localhost:8081

.PHONY: help setup lint lint-md lint-yaml lint-commits changelog up down reset ps logs health bootstrap demo intake-check ui-check events dxctl seed rls-check onboarding-check ledger-check seal-check tamper untamper workflow-check

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' Makefile | awk 'BEGIN {FS = ":.*## "} {printf "  %-20s %s\n", $$1, $$2}'

.env:
	cp .env.example .env

up: .env ## Start the services of PROFILE (default: core), wait until healthy, apply metadata
	$(COMPOSE) up -d --build --wait
	@$(MAKE) --no-print-directory bootstrap
	@$(MAKE) --no-print-directory seed

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
	@curl -fsS --retry 20 --retry-delay 3 --retry-all-errors -X POST "$(HASURA_URL)/v1/metadata" \
		-H "Content-Type: application/json" \
		-H "X-Hasura-Admin-Secret: $(HASURA_ADMIN_SECRET)" \
		-d @deploy/compose/demo/hasura/metadata.json && echo " Hasura metadata applied."

DXCTL := docker compose --env-file .env -f deploy/compose/docker-compose.yml --profile tools run --rm --build dxctl
SEED_TENANTS ?= company-a-steel company-b-logistics

dxctl: ## Run the tenant CLI, e.g. make dxctl ARGS="tenant list"
	@$(DXCTL) $(ARGS)

seed: ## Onboard the demo tenants (SEED_TENANTS) from their config packs; safe to repeat
	@for t in $(SEED_TENANTS); do $(DXCTL) tenant create tenants/$$t || exit 1; done

onboarding-check: ## Brief acceptance test: onboard company-c-cement from config only, log in, upload, disable
	@bash deploy/compose/demo/onboarding-check.sh

ledger-check: ## Check Carbon Ledger: event -> activity -> approval -> emission entry -> lineage
	@bash deploy/compose/demo/ledger-check.sh

workflow-check: ## Phase 4: different approval flows for A and B, purchase invoices go to Purchase Approval
	@bash deploy/compose/demo/workflow-check.sh

seal-check: ## Demo step 4: close and seal a period, tamper with a row, verification fails, restore
	@bash deploy/compose/demo/seal-check.sh

TENANT ?= company-a-steel
PERIOD ?= 2026-09
tamper: ## For the live demo: halve one emission entry of TENANT/PERIOD directly in PostgreSQL (untamper restores)
	@$(COMPOSE) exec -T postgres psql -U postgres -d ecotrace -c "UPDATE ledger.emission_entry SET co2e_kg = co2e_kg / 2 		WHERE id = (SELECT id FROM ledger.emission_entry WHERE tenant_id = '$(TENANT)' AND period = '$(PERIOD)' ORDER BY created_at LIMIT 1) 		RETURNING id, source_id, co2e_kg"

untamper: ## Undo make tamper
	@$(COMPOSE) exec -T postgres psql -U postgres -d ecotrace -c "UPDATE ledger.emission_entry SET co2e_kg = co2e_kg * 2 		WHERE id = (SELECT id FROM ledger.emission_entry WHERE tenant_id = '$(TENANT)' AND period = '$(PERIOD)' ORDER BY created_at LIMIT 1) 		RETURNING id, source_id, co2e_kg"

rls-check: ## Prove that PostgreSQL denies cross-tenant reads and writes for the service role
	@bash deploy/compose/demo/rls-check.sh

demo: ## Run the scripted core demo (identity, gateway, tenant isolation)
	@bash deploy/compose/demo/demo.sh

intake-check: ## Check document upload, extraction and tenant isolation (CHECK_IMAGES=1 also tests photos, needs AI)
	@bash deploy/compose/demo/intake-check.sh

events: ## Show the latest document events of TENANT (default company-a-steel) from NATS
	@$(COMPOSE) exec -T document-intake python - $(or $(TENANT),company-a-steel) < deploy/compose/demo/events.py

PLAYWRIGHT_IMAGE := mcr.microsoft.com/playwright/python:v1.64.0-noble
ui-check: ## Browser smoke test of the demo console; screenshots in /tmp/ecotrace-ui
	@mkdir -p /tmp/ecotrace-ui
	docker run --rm --network host -e DEMO_USER_PASSWORD -e EXPECT_SEAL -e SCREENSHOT_DIR=/shots \
		-v "$(CURDIR)/deploy/compose/demo:/tests:ro" -v /tmp/ecotrace-ui:/shots $(PLAYWRIGHT_IMAGE) \
		bash -c "pip install -q --root-user-action=ignore playwright==1.64.0 && python /tests/ui-check.py"

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
