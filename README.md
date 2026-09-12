# Ornithopter CAD — parametric wingtip + agent-driven CAD loop

[![ci](https://github.com/wrbell/ornithopter-cad/actions/workflows/ci.yml/badge.svg)](https://github.com/wrbell/ornithopter-cad/actions/workflows/ci.yml)

Parametric S1223 wingtip (TPU shell, FDM-printed) for an 8-wing flapping-wing (ornithopter) drone.
Edit the `CONFIG` dict at the top of `wingtip.py`, run it, look at the PNGs, read the mass report. The same
geometry is exposed to Claude Code through [agentcad](https://agentcad.dev) (versioned runs, previews, measure,
diff, an A/B viewer, and an MCP server), so the design can be iterated by talking to an agent.

No FreeCAD: geometry is built headless with **CadQuery (OpenCascade)** from pip, rendered with **pyvista**
off-screen, 2D work in **numpy + shapely**. Everything lives in this repo except the pip wheels.

## Setup (macOS or Linux; Python 3.10–3.12)

```bash
make setup                 # .venv (pipeline) + .venv-agentcad (agentcad CLI + MCP server), ~10 min first time
make run                   # full build: STEP/STL + PNGs + report
make test                  # fast unit tests (no OCCT)
make slow                  # real OCCT build checks (~30 s)
make agentcad-smoke        # end-to-end check of the agentcad integration
```

Two venvs are deliberate. agentcad 0.6 pins the OpenCascade binding to the 7.8 generation; the pipeline runs
on 7.9. The two binary builds cannot share a venv, and when agentcad moves to 7.9 its own CadQuery extra will
collide with build123d's VTK-free binding, so keeping them apart is what stays stable. `make setup` builds both;
you never activate either.

| venv | runs | kernel |
|---|---|---|
| `.venv` | `wingtip.py`, tests, pyvista renders, `out/report.txt` | cadquery 2.8 / OCP 7.9 |
| `.venv-agentcad` | `agentcad` CLI, MCP server, `models/wingtip_agentcad.py` | cadquery 2.7 / OCP 7.8 |

## Run

```bash
.venv/bin/python wingtip.py                                   # build + STEP/STL + PNGs + report
.venv/bin/python wingtip.py --set wall_thickness_mm=1.6       # override any scalar CONFIG key (repeatable)
.venv/bin/python wingtip.py --airfoil data/airfoils/other.dat  # any Selig/Lednicer .dat, or a UIUC name
.venv/bin/python wingtip.py --solid                           # outer loft only (fast)
.venv/bin/python wingtip.py --no-render                       # skip PNGs
```

Outputs in `out/`:

| file | what |
|---|---|
| `wingtip.step`, `wingtip.stl` | for any CAD package / slicer (STL at 0.02 mm, binary; gitignored) |
| `wingtip_top.png` | planform, looking down: LE at top, span to the right; root/tip outlines + quarter-chord overlaid |
| `wingtip_front.png` | from the nose: span, dihedral, thickness taper |
| `wingtip_side.png` | from the tip looking inboard: profile, washout |
| `wingtip_root.png` | the open root face: wall ring, cavity, pillars, holes |
| `wingtip_iso.png`, `wingtip_iso_root.png` | perspectives (the second looks into the open root) |
| `section.png` | root and tip sections with cavity, holes, bosses, min clearances; placed sections showing twist |
| `planform.png` | LE/TE/quarter-chord, hole positions and depths |
| `report.txt`, `wingtip_run.json` | mass report, wall-thickness table, all config + checks |

## Using with Claude Code

`docs/HANDOFF.md` is the one-page version for a new machine. In short: `make setup`, then `claude` in this
folder. The first launch asks to approve the project's `agentcad` MCP server (defined in `.mcp.json`); the
`agentcad` skill in `.claude/skills/` and the project rules in `CLAUDE.md` are discovered automatically.

Two roles:

| tool | use it for |
|---|---|
| `wingtip.py` (`make run`) | the engineering deliverables: STEP/STL, the five renders, the mass and wall-thickness table |
| agentcad (`make agentcad-run LABEL=x ARGS="--params k=v"`) | fast iteration: versioned runs under `build/`, four-view preview, iso/top/front renders, `measure`, `diff` between versions, `check-spec`, a browser A/B viewer |

Example prompts: "thin the wall to 1.6 mm and show me the root view", "move the aft hole to 58 % chord and
report the clearances", "compare 6° and 8° washout side by side".

Notes:

- agentcad's `metrics.volume` is OpenCascade's analytic integration, which is about 25 % low on this spline
  loft; mass always comes from `out/report.txt` (triangulated volume). The model script also emits a 2D mass
  estimate in the agentcad `warnings` array.
- agentcad artifacts go to `build/` (gitignored). `make agentcad-import LABEL=x` adopts the main-kernel
  `out/wingtip.step` as an agentcad version for measuring and diffing.
- `make agentcad-guide` refreshes the generated skill and the `AGENTS.md` block after upgrading agentcad.
- Moved or renamed the folder? `rm -rf .venv .venv-agentcad build && make setup`.
- agentcad is Apache-2.0 and installed from PyPI, not vendored.

## Coordinate frame

* **x** chordwise, positive aft, root LE at 0 · **y** spanwise, positive outboard, rib face at 0 · **z** up.
* Sections are scaled to chord(f), rotated about their **quarter-chord point** by `washout_deg · f`
  (positive = nose down), then shifted aft by `span · f · tan(le_sweep)` and up by `span · f · tan(dihedral)`.
  Sections stay in planes y = const, so the ruled loft's cross-section at y is exactly the linear blend of
  the root and tip sections; validation and the mass table use that same blend.

## Airfoil handling (`ornitho/airfoil.py`)

* Loader accepts Selig (UIUC), Lednicer (with/without count line), and 3-column XYZ exports,
  in any start point, direction, units or rotation. The **file's frame is kept exactly** when the TE is at
  (1, 0) and the nose at x ≈ 0 (stock S1223), only scaled when it is in mm, and re-fitted (LE → origin,
  TE → (1, 0)) otherwise; the report says which happened.
* `te_truncate_pct` cuts both surfaces at `1 − pct/100` chord with a vertical face. **The chord is not
  rescaled**: `root_chord_mm` is the nominal S1223 chord so the outer surface matches a rib cut from the same
  file; the blunt face sits at 163.35 mm for a 165 mm root. Note the S1223 is very thin aft: a 1 % cut gives a
  0.42 mm TE at root and 0.20 mm at the tip.
* `gurney_flap_pct` adds a tab hanging down from the lower TE corner, `gurney_thickness_mm` thick (absolute,
  so it is the same thickness at root and tip).
* To try another airfoil: drop the `.dat` in `data/airfoils/` and set `"airfoil"` (or `--airfoil`); any UIUC
  name is also fetched automatically. If a file already has a blunt TE, set `te_truncate_pct` to 0.

## Geometry (`ornitho/geometry.py`, `ornitho/wing.py`)

* Outer skin: ruled loft (OCCT `ThruSections`, compatibility check off so the two blunt-TE vertices are never
  mis-matched) between the root and tip wires. Each wire = one interpolating spline through 159 points +
  a straight TE edge (+ tab edges with a Gurney).
* Hollow: the cavity is a second ruled loft of the sections **eroded by the wall thickness in 2D
  (shapely)**; where the section is thinner than 2× wall (aft ~15–35 % of chord) it is left solid. The cavity
  starts 1 mm outside the root face (open root) and stops one wall short of the tip (closed tip cap).
  `root_solid_mm > 0` fills the root instead.
* Mount holes: spanwise bores from the root face to `hole_depth_mm`, matching the rib's through-holes.
  Each gets a boss web: a full-height slab `hole r + boss_wall_mm` either side of the bore, subtracted from the
  cavity before the cavity is subtracted from the skin, so every boss bridges both skins (a cylindrical boss
  can float inside a tall cavity; the build refuses any body that is not a single solid).
* **Validation (fails loudly):** every hole padded by `hole_min_wall_mm` must sit inside the section outline
  at 7 stations along its depth (the section shrinks, sweeps and twists over the depth). Holes are placed
  on the camber line unless `z_pct` is given (`HoleValidationError` otherwise).
* Mass properties use a fine triangulation. OCCT's analytic `Shape.Volume()` was measured ~25 % low on these
  spline solids and is not used.

## Development

```bash
make setup    # both venvs + deps
make test     # fast unit tests
make slow     # OCCT build tests
make lint     # ruff
make run      # full build
make agentcad-dry LABEL=v1 / agentcad-run LABEL=v1 / agentcad-smoke / agentcad-guide / agentcad-reset
```
CI (GitHub Actions) runs lint, the fast suite, the OCCT suite and a headless default build in one job, and the
agentcad contract check (`smoke_agentcad.py`) in a second job.

## Loop

1. edit `CONFIG` (or ask Claude) → 2. `make run` or `make agentcad-run` → 3. look at the PNGs → 4. read
`out/report.txt` → repeat. Every render is regenerated on every run; the title line of each PNG carries the key
parameters.
