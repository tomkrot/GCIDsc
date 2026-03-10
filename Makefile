.PHONY: help install dev lint test export diff apply clean

PYTHON ?= python3
CONFIG ?= config/tenant.yaml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install package
	$(PYTHON) -m pip install -e .

dev: ## Install with dev dependencies
	$(PYTHON) -m pip install -e ".[dev]"
	pre-commit install

lint: ## Lint with ruff + mypy
	ruff check src/ tests/
	mypy src/gwsdsc/

test: ## Run tests
	pytest --cov=gwsdsc --cov-report=term-missing

export: ## Export tenant config (CONFIG=config/tenant.yaml)
	gwsdsc export --config $(CONFIG)

diff: ## Diff last two exports
	gwsdsc diff --baseline artifacts/previous --target artifacts/latest

apply: ## Apply config (dry-run by default)
	gwsdsc apply --config $(CONFIG) --source artifacts/latest --plan

clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
