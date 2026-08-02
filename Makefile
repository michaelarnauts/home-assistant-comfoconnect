check:
	@poetry run ruff check
	@poetry run ruff format --check

test:
	@poetry run pytest

codefix:
	@poetry run ruff check --fix
	@poetry run ruff format

.PHONY: check codefix test
