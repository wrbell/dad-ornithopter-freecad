PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

.PHONY: setup smoke run test slow lint fmt clean

setup:            ## create the venv and install pinned dependencies
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	$(BIN)/python -c "import cadquery, pyvista, shapely; print('ok: cadquery', cadquery.__version__)"

smoke:            ## toolchain check: extrude the root section, export, render
	$(BIN)/python smoke.py

run:              ## full wingtip build + STEP/STL + PNGs + report
	$(BIN)/python wingtip.py

test:             ## fast unit tests (no OCCT)
	$(BIN)/python -m pytest -q

slow:             ## OCCT geometry tests
	$(BIN)/python -m pytest -q -m slow

lint:             ## ruff lint + format check
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

fmt:              ## ruff auto-fix + format
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

clean:
	rm -rf out/*.step out/*.stl .pytest_cache $(shell find . -name __pycache__ -not -path './.venv/*')
