# VirtualLab-Copilot — common dev commands.
# Usage:  make <target>

PYTHON ?= python
PIP    ?= $(PYTHON) -m pip

.PHONY: help setup seed test lint run-api run-app run docker-build docker-up docker-down clean

help:
	@echo "Targets:"
	@echo "  setup         Create venv (./.venv) and install requirements"
	@echo "  seed          Generate synthetic SQLite database"
	@echo "  test          Run pytest"
	@echo "  run-api       Start FastAPI on http://localhost:8000"
	@echo "  run-app       Start Streamlit on http://localhost:8501"
	@echo "  run           Start API in background and Streamlit in foreground"
	@echo "  docker-build  Build the docker image"
	@echo "  docker-up     docker-compose up (API + Streamlit)"
	@echo "  docker-down   docker-compose down"
	@echo "  clean         Remove caches and the local database"

setup:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && $(PIP) install --upgrade pip && $(PIP) install -r requirements.txt
	@echo "Done. Activate with: source .venv/bin/activate"

seed:
	$(PYTHON) scripts/seed_db.py --force

test:
	$(PYTHON) -m pytest -ra

run-api:
	$(PYTHON) -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

run-app:
	$(PYTHON) -m streamlit run src/frontend/app.py --server.port 8501

run:
	$(PYTHON) -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &  \
	  sleep 2 && $(PYTHON) -m streamlit run src/frontend/app.py --server.port 8501

docker-build:
	docker build -t virtuallab-copilot:latest .

docker-up:
	docker compose up --build

docker-down:
	docker compose down

clean:
	rm -rf .pytest_cache __pycache__ */__pycache__ */**/__pycache__
	rm -f data/virtuallab.db
