# Ornithopter wingtip — parametric CAD + render loop

[![ci](https://github.com/wrbell/dad-ornithopter-freecad/actions/workflows/ci.yml/badge.svg)](https://github.com/wrbell/dad-ornithopter-freecad/actions/workflows/ci.yml)

Parametric S1223 wingtip (TPU shell, FDM-printed) for an 8-wing flapping-wing (ornithopter) drone.
Edit the `CONFIG` dict at the top of `wingtip.py`, run it, look at the PNGs, read the mass report.

No FreeCAD: geometry is built headless with **CadQuery 2.8 (OCCT 7.9)** from pip, rendered with
**pyvista** off-screen, 2D work in **numpy + shapely**. Everything lives in this repo except the pip wheels.

## Setup (macOS, Apple Silicon; any Python 3.11–3.13 works)

```bash
python3 -m venv .venv                      # e.g. /Users/willem/anaconda3/bin/python3
.venv/bin/pip install -r requirements.txt
.venv/bin/python smoke.py                  # toolchain check: extrudes the root section, exports, renders
.venv/bin/python -m pytest                 # fast unit tests (no OCCT)
.venv/bin/python -m pytest -m slow         # real OCCT build checks (~30 s)
```

## Run

```bash
.venv/bin/python wingtip.py                                   # build + STEP/STL + PNGs + report
.venv/bin/python wingtip.py --set wall_thickness_mm=1.6       # override any scalar CONFIG key (repeatable)
.venv/bin/python wingtip.py --airfoil data/airfoils/other.dat  # any Selig/Lednicer .dat
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
  Each gets a boss (pillar) of radius `hole r + boss_wall_mm`, made by subtracting the pillar from the cavity
  before the cavity is subtracted from the skin, so bosses merge with the skin without coincident-face booleans.
* **Validation (fails loudly):** every hole padded by `hole_min_wall_mm` must sit inside the section outline
  at 7 stations along its depth (the section shrinks, sweeps and twists over the depth). Holes are placed
  on the camber line unless `z_pct` is given (`HoleValidationError` otherwise).
* Mass properties use a fine triangulation. OCCT's analytic `Shape.Volume()` was measured ~25 % low on these
  spline solids and is not used.

## Development

```bash
make setup    # venv + deps
make test     # fast unit tests
make slow     # OCCT build tests
make lint     # ruff
make run      # full build
```
CI (GitHub Actions) runs lint, the fast suite and the OCCT suite on every push.

## Loop

1. edit `CONFIG` → 2. `python wingtip.py` → 3. look at `out/*.png` → 4. read `out/report.txt` → repeat.
Every render is regenerated on every run; the title line of each PNG carries the key parameters.
