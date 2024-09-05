check:
	@poetry run ruff check
	@poetry run ruff format --check

codefix:
	@poetry run ruff check --fix
	@poetry run ruff format

.PHONY: check codefix
