.PHONY: ruff ruff-check check-ruff

check-ruff:
	@command -v ruff >/dev/null 2>&1 || (echo "❌ Ruff is not installed. Please run the Anaconda(miniconda) setup to trigger the installation"; exit 1)

ruff: check-ruff
	@echo "🕵🏻 Formatting and fixing with Ruff..."
	ruff format .
	ruff check --fix .

ruff-check: check-ruff
	@echo "🕵🏻 Checking formatting and lint..."
	ruff format --check .
	ruff check .