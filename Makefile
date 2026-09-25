.PHONY: demo test lint stop
demo:
	docker compose up -d --build
test:
	uv run pytest -q
lint:
	uv run ruff check .
stop:
	docker compose stop
