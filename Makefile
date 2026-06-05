.PHONY: help install dev stop logs migrate migration shell test lint format

PYTHON := .venv/bin/python
UV := .venv/bin/uvicorn
ALEMBIC := .venv/bin/alembic

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  install     Create venv and install dependencies"
	@echo "  dev         Start DB + app (hot reload)"
	@echo "  stop        Stop all Docker containers"
	@echo "  logs        Tail DB logs"
	@echo "  migrate     Apply all pending migrations"
	@echo "  migration   Generate new migration (use: make migration msg='describe change')"
	@echo "  shell       Open psql shell inside the DB container"
	@echo "  lint        Run ruff linter"
	@echo "  format      Run black formatter"

install:
	python3.11 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

dev:
	docker compose up -d --wait
	$(UV) app.main:app --reload

stop:
	docker compose down

clear:
	docker compose down -v

logs:
	docker compose logs -f db

migrate:
	$(ALEMBIC) upgrade head

migration:
	$(ALEMBIC) revision --autogenerate -m "$(msg)"

shell:
	docker exec -it vetlanh_postgres psql -U vetlanh -d vetlanh_db

lint:
	.venv/bin/ruff check app/

format:
	.venv/bin/black app/
