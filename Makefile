.PHONY: all build tests examples sync clean reset

all: build

build:
	@uv build

tests:
	@cd tests && uv run shedskin test

test: tests

examples:
	@cd examples && uv run shedskin test

clean:
	@rm -rf build dist

reset: clean
	@rm -rf .venv
	@rm -rf tests/build examples/build

sync:
	@uv sync
