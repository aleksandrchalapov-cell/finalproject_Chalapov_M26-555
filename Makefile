.PHONY: install run lint build package-install

install:
	uv sync

run:
	uv run valutatrade

lint:
	uv run ruff check .

build:
	rm -rf dist
	uv build

package-install:
	uv tool install dist/*.whl
