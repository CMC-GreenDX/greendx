.DEFAULT_GOAL := help

PYTHON ?= python

.PHONY: help setup lint lint-md lint-yaml lint-commits changelog

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-20s %s\n", $$1, $$2}'

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
