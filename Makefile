.PHONY: all build tests test tests-conan examples examples-conan \
		sync clean reset

all: build

build:
	@uv build

tests:
	@cd tests && uv run shedskin test

test: tests

tests-conan:
	@cd tests && uv run shedskin test --conan

examples:
	@cd examples && uv run shedskin test

examples-conan:
	@cd examples && uv run shedskin test --conan

clean:
	@rm -rf build dist

reset: clean
	@rm -rf .venv
	@rm -rf tests/build examples/build

sync:
	@uv sync
