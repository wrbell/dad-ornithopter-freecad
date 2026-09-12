PY ?= python3
VENV = .venv
BIN = $(VENV)/bin
VENV_AC = .venv-agentcad
ACBIN = $(VENV_AC)/bin
AGENTCAD = $(ACBIN)/agentcad
MODEL = models/wingtip_agentcad.py
LABEL ?= dev
ARGS ?=
export AGENTCAD_RUN_TIMEOUT_S ?= 600

.PHONY: setup setup-main setup-agentcad smoke run test slow lint fmt clean \
        agentcad-dry agentcad-run agentcad-import agentcad-smoke agentcad-guide agentcad-reset mcp

setup: setup-main setup-agentcad   ## both toolchains (this is all a new machine needs)

setup-main:                        ## .venv: full pipeline, tests, pyvista renders, report
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	$(BIN)/python -c "import cadquery, pyvista, shapely, ornitho; print('ok: cadquery', cadquery.__version__)"

setup-agentcad:                    ## .venv-agentcad: agentcad CLI + MCP server (OpenCascade 7.8 generation)
	$(PY) -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 'agentcad needs Python 3.10-3.12: make setup-agentcad PY=python3.12')"
	$(PY) -m venv $(VENV_AC)
	$(ACBIN)/pip install --upgrade pip
	$(ACBIN)/pip install -r requirements-agentcad.txt
	$(ACBIN)/python -c "import agentcad, cadquery, build123d, ornitho.wing; print('ok: agentcad', agentcad.__version__, '/ cadquery', cadquery.__version__)"
	test -f build/agentcad.json || $(AGENTCAD) init --name ornithopter-cad --runtime cadquery --no-agent-setup

smoke:            ## toolchain check: extrude the root section, export, render
	$(BIN)/python smoke.py

run:              ## full wingtip build + STEP/STL + PNGs + report (authoritative mass numbers)
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

agentcad-dry:     ## validity + metrics of the model, no version consumed
	$(AGENTCAD) run $(MODEL) --label $(LABEL) --dry-run --no-daemon $(ARGS)

agentcad-run:     ## versioned run: STEP + preview + iso/top/front renders (+ diff vs previous)
	$(AGENTCAD) run $(MODEL) --label $(LABEL) --render iso,top,front --no-daemon $(ARGS)

agentcad-import:  ## adopt the main-kernel STEP from `make run` as an agentcad version
	$(AGENTCAD) import out/wingtip.step --label $(LABEL) --no-daemon

agentcad-smoke:   ## end-to-end contract check of the agentcad integration (same script CI runs)
	$(BIN)/python smoke_agentcad.py --agentcad $(AGENTCAD)

agentcad-guide:   ## refresh the generated skill + AGENTS.md block after upgrading agentcad
	$(AGENTCAD) skill install
	$(AGENTCAD) instructions install --target agents

agentcad-reset:   ## wipe agentcad version history (also needed after moving/renaming the folder)
	rm -rf build && $(AGENTCAD) init --name ornithopter-cad --runtime cadquery --no-agent-setup

mcp:              ## run the MCP server in the foreground (what .mcp.json launches)
	$(ACBIN)/python -m agentcad.mcp

clean:
	rm -rf out/*.step out/*.stl ci_out .pytest_cache .ruff_cache $(shell find . -name __pycache__ -not -path './.venv*/*' -not -path './build/*')
