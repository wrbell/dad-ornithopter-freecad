#!/usr/bin/env python
"""Parametric ornithopter wingtip: edit CONFIG, run, look at out/*.png, read out/report.txt.

    .venv/bin/python wingtip.py                      # full build, export, render, report
    .venv/bin/python wingtip.py --set wall_thickness_mm=1.6 --set washout_deg=6
    .venv/bin/python wingtip.py --airfoil data/airfoils/other.dat
    .venv/bin/python wingtip.py --no-render          # geometry + report only
    .venv/bin/python wingtip.py --solid              # skip hollowing/holes (fast sanity check)

Coordinate frame: x chordwise aft (root LE at 0), y spanwise outboard (rib face at 0), z up.
"""

from __future__ import annotations

import argparse
import ast
import sys
import time
from pathlib import Path

# ----------------------------------------------------------------------------- #
# CONFIG — the only block you normally edit
# ----------------------------------------------------------------------------- #
CONFIG = {
    "airfoil": "s1223",  # UIUC name (auto-fetched to data/airfoils/) or a path to a .dat file
    "root_chord_mm": 165.0,  # matches the existing rib exactly (full S1223, unmodified)
    "tip_chord_mm": 80.0,  # starting guess
    "span_mm": 270.0,  # outer 27 % of a 1000 mm semi-span
    "le_sweep_deg": 15.0,  # leading-edge sweep, starting guess
    "washout_deg": 8.0,  # nose-down twist at the tip, linear from the root, about the quarter chord
    "dihedral_deg": 0.0,
    "wall_thickness_mm": 2.5,  # TPU shell wall (hollow); see the wall table in the report
    "te_truncate_pct": 1.0,  # blunt TE cut at 1 - pct/100 of chord; chord is NOT rescaled
    "gurney_flap_pct": 0.0,  # 1-2 % chord tab under consideration; 0 = off
    "gurney_thickness_mm": 1.2,
    # mount holes: spanwise through the root face, matching the rib's through-holes.
    # x_pct = % of root chord from the LE; z_pct = % of root chord above the chord line
    # (None = centred between the skins, i.e. on the camber line). Placeholders until measured.
    "mount_holes": [
        {"name": "fwd", "x_pct": 18.0, "d_mm": 4.2, "z_pct": None},
        {"name": "mid", "x_pct": 40.0, "d_mm": 4.2, "z_pct": None},
        {"name": "aft", "x_pct": 65.0, "d_mm": 4.2, "z_pct": None},
    ],
    "hole_depth_mm": 15.0,  # how far the holes (and their bosses) run in from the root face
    "boss_wall_mm": None,  # boss radius = hole radius + this (None = wall_thickness_mm)
    "hole_min_wall_mm": 1.0,  # VALIDATED: minimum skin material around every hole, all along its depth
    "root_solid_mm": 0.0,  # >0 fills the first N mm at the root solid (default: open root face)
    "density_g_cm3": 1.20,  # TPU 85A
    "wall_table_mm": [1.2, 1.6, 2.0, 2.5, 3.0],
    "target_mass_g": 110.0,
}
OUT_DIR = Path("out")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override a scalar CONFIG entry (repeatable), e.g. --set wall_thickness_mm=1.6",
    )
    ap.add_argument("--airfoil", help="path to a .dat file (Selig/Lednicer/XYZ) or a UIUC airfoil name")
    ap.add_argument("--out", default=str(OUT_DIR), help="output directory (default out/)")
    ap.add_argument("--no-render", action="store_true", help="skip PNG rendering")
    ap.add_argument("--solid", action="store_true", help="outer loft only: no cavity, no holes")
    ap.add_argument("--no-exact", action="store_true", help="skip OCCT triangulated mass properties (faster)")
    return ap.parse_args(argv)


def apply_overrides(cfg: dict, sets: list[str]) -> dict:
    cfg = dict(cfg)
    for item in sets:
        if "=" not in item:
            raise SystemExit(f"--set expects KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        try:
            cfg[k] = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            cfg[k] = v
    return cfg


def main(argv=None) -> int:
    args = parse_args(argv)
    from ornitho import geometry as geo
    from ornitho import render, report, wing
    from ornitho.config import WingConfig

    cfg_dict = apply_overrides(CONFIG, args.set)
    if args.airfoil:
        cfg_dict["airfoil"] = args.airfoil
    cfg = WingConfig.from_dict(cfg_dict)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    print(f"[1/5] building wingtip ({'solid' if args.solid else 'hollow + holes'}) ...")
    b = wing.build(cfg, hollow=not args.solid, holes=not args.solid)
    print(f"      done in {b.timings['total']:.1f} s; checks: {b.checks}")

    print("[2/5] exporting STEP + STL ...")
    geo.export(b.body, out / "wingtip.step", out / "wingtip.stl")

    print("[3/5] 2D diagnostics ...")
    pngs = [
        render.plot_planform(cfg, b.holes, out / "planform.png"),
        render.plot_sections(
            cfg, b.foil, b.root3, b.tip3, b.holes, out / "section.png", cfg.wall_thickness_mm, tip_foil=b.tip_foil
        ),
    ]

    if not args.no_render:
        print("[4/5] rendering views ...")
        verts, tris = geo.tessellate(b.body)
        title = (
            f"root {cfg.root_chord_mm:g} / tip {cfg.tip_chord_mm:g} / span {cfg.span_mm:g} mm, "
            f"sweep {cfg.le_sweep_deg:g}°, "
            f"washout {cfg.washout_deg:g}°, wall {cfg.wall_thickness_mm:g} mm"
        )
        pngs += render.render_views(verts, tris, out, prefix="wingtip", overlays=b.overlays(), title=title)
    else:
        print("[4/5] rendering skipped")

    print("[5/5] report ...")
    rep = report.build_report(b, exact=not args.no_exact)
    rep["outputs"] = {"step": str(out / "wingtip.step"), "stl": str(out / "wingtip.stl"), "png": [str(p) for p in pngs]}
    txt, js = report.write_report(rep, out)
    print()
    print(report.format_report(rep))
    print()
    print("outputs:", ", ".join(str(p) for p in [out / "wingtip.step", out / "wingtip.stl", txt, js]))
    for p in pngs:
        print("  png:", p)
    print(f"total {time.perf_counter() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
