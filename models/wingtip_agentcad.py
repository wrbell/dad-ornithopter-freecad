"""agentcad-runnable wingtip (CadQuery runtime). Same geometry as wingtip.py, built by ornitho.wing.build().

    make agentcad-dry LABEL=v1                                   # validity + metrics, no version consumed
    make agentcad-run LABEL=thin ARGS="--params wall_thickness_mm=1.6"
    .venv-agentcad/bin/agentcad run models/wingtip_agentcad.py --label v1 --no-daemon
    .venv/bin/python models/wingtip_agentcad.py                  # standalone sanity check on the main kernel

Contract with agentcad / CQGI (see CLAUDE.md):
* only top-level `name = <number | "str" | True/False>` lines are --params: no `= None`, no tuples,
  no negative literals here (CQGI prints to stdout or silently skips them);
* never print(): agentcad's stdout is the JSON response; warnings.warn() is the one free-text channel;
* show_object() needs a cq.Workplane, not a bare cq.Solid.
"""

# --- PARAMS (overridable with --params key=value,key=value) ------------------------------------
airfoil = "s1223"  # UIUC name (cached in data/airfoils/) or a path to a .dat file
root_chord_mm = 165.0  # matches the existing rib exactly (full S1223, unmodified)
tip_chord_mm = 80.0
span_mm = 270.0
le_sweep_deg = 15.0
washout_deg = 8.0  # nose-down at the tip, about the quarter chord
dihedral_deg = 0.0
wall_thickness_mm = 2.5
te_truncate_pct = 1.0
gurney_flap_pct = 0.0
gurney_thickness_mm = 1.2
hole_d_mm = 4.2
hole_fwd_x_pct = 18.0  # % of root chord from the LE; z sits on the camber line
hole_mid_x_pct = 40.0
hole_aft_x_pct = 65.0
hole_depth_mm = 15.0
hole_min_wall_mm = 1.0  # VALIDATED minimum skin around every hole along its depth
root_solid_mm = 0.0
density_g_cm3 = 1.2
hollow = True
holes = True
# --- machinery: nothing below is a parameter ---------------------------------------------------
import sys
import warnings

# agentcad's daemon and MCP server are long-lived processes: drop any cached ornitho so edits to
# ornitho/*.py are seen on every run (this file itself is always re-read by agentcad).
for _m in [m for m in sys.modules if m == "ornitho" or m.startswith("ornitho.")]:
    del sys.modules[_m]

import cadquery as cq  # pre-injected by agentcad; explicit so the file also runs standalone

from ornitho.config import WingConfig
from ornitho.report import shell_volume_2d
from ornitho.wing import build

if "show_object" not in globals():  # plain `python models/wingtip_agentcad.py`

    def show_object(obj, **_):
        s = obj.val()
        bb = s.BoundingBox()
        sys.stderr.write(
            f"standalone: valid={s.isValid()}  x {bb.xmin:.1f}..{bb.xmax:.1f}  "
            f"y {bb.ymin:.1f}..{bb.ymax:.1f}  z {bb.zmin:.1f}..{bb.zmax:.1f} mm\n"
        )


cfg = WingConfig(
    airfoil=airfoil,
    root_chord_mm=root_chord_mm,
    tip_chord_mm=tip_chord_mm,
    span_mm=span_mm,
    le_sweep_deg=le_sweep_deg,
    washout_deg=washout_deg,
    dihedral_deg=dihedral_deg,
    wall_thickness_mm=wall_thickness_mm,
    te_truncate_pct=te_truncate_pct,
    gurney_flap_pct=gurney_flap_pct,
    gurney_thickness_mm=gurney_thickness_mm,
    mount_holes=[
        ("fwd", hole_fwd_x_pct, hole_d_mm),
        ("mid", hole_mid_x_pct, hole_d_mm),
        ("aft", hole_aft_x_pct, hole_d_mm),
    ],
    hole_depth_mm=hole_depth_mm,
    hole_min_wall_mm=hole_min_wall_mm,
    root_solid_mm=root_solid_mm,
    density_g_cm3=density_g_cm3,
)
b = build(cfg, hollow=hollow, holes=holes)  # HoleValidationError / RuntimeError -> agentcad status "failed"

if hollow and holes:
    est = shell_volume_2d(cfg, b.root3, b.tip3, b.holes, cfg.wall_thickness_mm)
    warnings.warn(
        f"info: est. mass {est['mass_g']:.1f} g at wall {cfg.wall_thickness_mm:g} mm (2D shell integration; "
        "the authoritative mass / wall table is out/report.txt from `python wingtip.py`)",
        stacklevel=1,
    )
    for h in b.holes:
        if h["min_clearance"] < 0.5:
            warnings.warn(
                f"hole '{h['name']}' has only {h['min_clearance']:+.2f} mm beyond the {cfg.hole_min_wall_mm:g} mm "
                f"min wall at y={h['at_y']:.1f} mm",
                stacklevel=1,
            )

show_object(cq.Workplane("XY").newObject([b.body]), name="wingtip")
