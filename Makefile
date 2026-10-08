PYTHON ?= python3

.PHONY: install test lint demo api web build
install:
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps -e .
test:
	$(PYTHON) -m pytest
lint:
	$(PYTHON) -m ruff check src tests
demo:
	inflationweaver demo --out reports/demo
api:
	inflationweaver serve
web:
	cd web && npm ci && npm run dev
build:
	$(PYTHON) -m build --no-isolation
	cd web && npm ci && npm run build
