"""Toolchain smoke test: stock S1223 root section -> 20 mm extrusion -> STEP/STL -> PNGs.

Run this first on a new machine. If every PNG looks like a short airfoil
prism, the parser, spline wire, solid ops, exporters and off-screen renderer
all work.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

from ornitho import airfoil as af
from ornitho import geometry as geo
from ornitho import render
from ornitho.sections import Planform

OUT = Path("out")
CHORD = 165.0
LENGTH = 20.0


def main() -> int:
    t0 = time.time()
    path = af.fetch("s1223")
    foil = af.load(path, te_truncate_pct=1.0, n_per_surface=80)
    print(f"airfoil: {foil.name}  frame: {foil.frame.describe()}")
    print(f"  TE gap {foil.te_gap() * CHORD:.2f} mm, max thickness {foil.max_thickness()[1] * CHORD:.1f} mm")
    render.plot_airfoil(foil, OUT / "smoke_section.png", raw_loop=af.parse_dat(path), chord_mm=CHORD)

    st = Planform(CHORD, CHORD, LENGTH).station(0.0)
    pts3 = st.place_unit(foil.outline())
    wire = geo.outer_wire(pts3)
    solid = geo.extrude(wire, (0.0, LENGTH, 0.0))
    print(f"solid valid={solid.isValid()}  volume={geo.volume(solid) / 1000:.3f} cm³ "
          f"(expected {foil.area() * CHORD**2 * LENGTH / 1000:.3f})  area={geo.area(solid) / 100:.2f} cm²")
    bb = geo.bbox(solid)
    print("  bbox x[%.2f, %.2f] y[%.2f, %.2f] z[%.2f, %.2f]" % (bb["xmin"], bb["xmax"], bb["ymin"], bb["ymax"], bb["zmin"], bb["zmax"]))

    geo.export(solid, OUT / "smoke.step", OUT / "smoke.stl")
    print(f"STEP round-trip volume: {geo.step_roundtrip_volume(OUT / 'smoke.step') / 1000:.3f} cm³")
    verts, tris = geo.tessellate(solid)
    print(f"tessellation: {len(verts)} verts, {len(tris)} tris")
    pngs = render.render_views(verts, tris, OUT, prefix="smoke",
                               overlays={"root outline": pts3, "quarter chord": np.array([[0.25 * CHORD, 0, 0], [0.25 * CHORD, LENGTH, 0]])},
                               title=f"smoke test: S1223 @ {CHORD:g} mm chord extruded {LENGTH:g} mm")
    for p in pngs:
        print("  wrote", p)
    print(f"done in {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
