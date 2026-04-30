.PHONY: wordome bootstrap-snowflake smoke-check ruff ruff-check check-ruff

wordome:
	@wordome

bootstrap-snowflake:
	@conda run -n wordome_env python scripts/bootstrap_snowflake.py

smoke-check:
	@conda run -n wordome_env python scripts/run_smoke_checks.py

check-ruff:
	@conda run -n wordome_env ruff --version >/dev/null 2>&1 || (echo "❌ Ruff is not available in the wordome_env conda environment."; exit 1)

ruff: check-ruff
	@echo "🕵🏻 Formatting and fixing with Ruff..."
	@conda run -n wordome_env ruff format .
	@conda run -n wordome_env ruff check --fix .

ruff-check: check-ruff
	@echo "🕵🏻 Checking formatting and lint..."
	@conda run -n wordome_env ruff format --check .
	@conda run -n wordome_env ruff check .
