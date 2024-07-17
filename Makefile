check:
	@poetry run ruff check

codefix:
	@poetry run ruff format
	@poetry run ruff check --fix

.PHONY: check codefix
