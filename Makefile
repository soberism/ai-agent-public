.PHONY: format format-check lint
format:
	cd frontend && npm run format
	cd backend && uv run ruff format src tests migrations infra

format-check:
	cd frontend && npm run format:check
	cd backend && uv run ruff format --check src tests migrations infra

lint:
	cd frontend && npm run lint
