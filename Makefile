.PHONY: setup venv install run worker migrate test lint clean

VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# ─── Environment ──────────────────────────────────────────────────
venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv
	$(PIP) install -r requirements.txt

setup: install
	$(PYTHON) setup.py

# ─── Run ──────────────────────────────────────────────────────────
run:
	$(VENV)/bin/uvicorn app:app --reload --host 0.0.0.0 --port 8000

worker:
	$(VENV)/bin/celery -A api.tasks.celery_app worker --loglevel=info

# ─── Database ─────────────────────────────────────────────────────
migrate:
	$(VENV)/bin/alembic upgrade head

migrate-down:
	$(VENV)/bin/alembic downgrade -1

# ─── Pipeline ─────────────────────────────────────────────────────
ingest:
	$(PYTHON) scripts/make_dataset.py

features:
	$(PYTHON) scripts/build_features.py

train:
	$(PYTHON) scripts/model.py --train

predict:
	$(PYTHON) scripts/model.py --predict

# ─── Testing ──────────────────────────────────────────────────────
test:
	$(VENV)/bin/pytest tests/ -v

test-cov:
	$(VENV)/bin/pytest tests/ -v --cov=. --cov-report=html

# ─── Quality ──────────────────────────────────────────────────────
lint:
	$(VENV)/bin/ruff check . --fix
	$(VENV)/bin/ruff format .

# ─── Frontend ─────────────────────────────────────────────────────
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# ─── Clean ────────────────────────────────────────────────────────
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
