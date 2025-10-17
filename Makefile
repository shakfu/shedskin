.PHONY: help install dev sync test test-unit test-exe test-ext \
		test-all test-modified test-single test-log clean build lint \
		format typecheck coverage docs

help:
	@echo "Shedskin Development Makefile"
	@echo ""
	@echo "Setup Commands:"
	@echo "  make install        Install project dependencies with uv"
	@echo "  make dev            Install development dependencies"
	@echo "  make sync           Sync dependencies with uv.lock"
	@echo ""
	@echo "Testing Commands:"
	@echo "  make test           Run pytest tests"
	@echo "  make test-unit      Run unit tests"
	@echo "  make test-exe       Run all executable tests (Linux/macOS)"
	@echo "  make test-ext       Run all tests as executables and extensions"
	@echo "  make test-all       Run all test suites (pytest + cmake)"
	@echo "  make test-modified  Run recently modified tests only"
	@echo "  make test-single    Run single test (usage: make test-single TEST=test_builtin_iter)"
	@echo "  make test-errs      Run error/warning message tests"
	@echo "  make test-log       Run all executable tests and store output in tests.log"
	@echo ""
	@echo "Quality Commands:"
	@echo "  make lint           Run mypy type checking"
	@echo "  make typecheck      Alias for lint"
	@echo "  make coverage       Run tests with coverage report"
	@echo ""
	@echo "Build Commands:"
	@echo "  make build          Build test example"
	@echo "  make clean          Clean build artifacts and caches"
	@echo "  make reset          Reset cmake build directory"
	@echo ""
	@echo "Other Commands:"
	@echo "  make docs           Build documentation (if available)"

# Setup commands
install:
	uv sync

dev:
	uv sync --dev

sync:
	uv sync

# Testing commands
test:
	cd tests && uv run pytest

test-unit:
	cd tests && uv run pytest unit/

test-exe:
	cd tests && uv run shedskin test -x

test-ext:
	cd tests && uv run shedskin test -xe

test-all:
	cd tests && uv run pytest
	cd tests && uv run shedskin test -xe

test-modified:
	cd tests && uv run shedskin test -x --modified

test-single:
	@if [ -z "$(TEST)" ]; then \
		echo "Error: TEST variable not set. Usage: make test-single TEST=test_builtin_iter"; \
		exit 1; \
	fi
	cd tests && uv run shedskin test --run $(TEST)

test-errs:
	cd tests && uv run shedskin test --run-errs

test-log:
	cd tests && uv run shedskin test --reset -x &> ../tests.log


# Quality commands
lint:
	uv run mypy shedskin/

typecheck: lint

coverage:
	cd tests && uv run pytest --cov=shedskin --cov-report=html --cov-report=term

# Build commands
build:
	uv run shedskin build test

clean:
	rm -rf build/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .tox/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

reset:
	rm -rf tests/build

# Documentation
docs:
	@echo "Documentation build not yet configured"
