# Developer shortcuts. Uses the project venv when present, else python3 on PATH.
PYTHON ?= $(firstword $(wildcard venv/bin/python .venv/bin/python) python3)

.PHONY: lint fmt test check audit sync lock

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

fmt:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest -v tests/

# Full local gate: lint + format check + pytest + pip-audit (see scripts/check_local.py).
check:
	$(PYTHON) scripts/check_local.py

audit:
	$(PYTHON) -m pip_audit -r requirements.txt

sync:
	$(PYTHON) -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt

# Re-compile hashed lock files from requirements.in / requirements-dev.in (needs pip-tools).
lock:
	$(PYTHON) -m piptools compile --generate-hashes --allow-unsafe --strip-extras -o requirements.txt requirements.in
	$(PYTHON) -m piptools compile --generate-hashes --allow-unsafe --strip-extras -c requirements.txt -o requirements-dev.txt requirements-dev.in
