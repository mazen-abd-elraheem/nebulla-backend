# ── Dev server (with auto-reload) ─────────────────────
dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ── Production server ─────────────────────────────────
start:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# ── Install dependencies ──────────────────────────────
install:
	pip install -r requirements.txt

# ── Tests ─────────────────────────────────────────────
test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

# ── DB migrations (Alembic) ───────────────────────────
migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(msg)"

# ── Docker ────────────────────────────────────────────
docker-build:
	docker build -t nebula-backend .

docker-run:
	docker run -p 8000:8000 --env-file .env nebula-backend

.PHONY: dev start install test test-unit test-integration migrate migration docker-build docker-run
