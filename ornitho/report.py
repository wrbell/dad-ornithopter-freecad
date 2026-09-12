"""Mass / area / volume report, including a wall-thickness trade table."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from shapely.geometry import Point

from . import geometry as geo
from .sections import polygon_xz, section_at


def shell_volume_2d(
    cfg, root3: np.ndarray, tip3: np.ndarray, holes: list[dict], wall: float, n_stations: int = 61
) -> dict:
    """Shell volume by span integration of (outer area - eroded area), plus pillars, minus bores.

    Exact to <1 % for the ruled loft; independent of any boolean succeeding.
    """
    y_start = -1.0 if cfg.root_solid_mm <= 0 else cfg.root_solid_mm
    ys = np.linspace(0.0, cfg.span_mm, n_stations)
    a_out = np.empty_like(ys)
    a_in = np.zeros_like(ys)
    for i, y in enumerate(ys):
        poly = polygon_xz(section_at(root3, tip3, y / cfg.span_mm))
        a_out[i] = poly.area
        if max(y_start, 0.0) <= y <= cfg.span_mm - wall:
            er = poly.buffer(-wall, join_style="mitre", mitre_limit=2.0)
            a_in[i] = er.area
    v_outer = np.trapezoid(a_out, ys)
    v_cavity = np.trapezoid(a_in, ys)
    # pillars: boss circle ∩ cavity at the root, over the pillar length; bores through everything
    v_pillars = 0.0
    v_bores = 0.0
    root_poly = polygon_xz(section_at(root3, tip3, 0.0))
    cav_root = root_poly.buffer(-wall, join_style="mitre", mitre_limit=2.0)
    for h in holes:
        boss = Point(h["x"], h["z"]).buffer(h["r_boss"], 64)
        v_pillars += boss.intersection(cav_root).area * (cfg.hole_depth_mm + wall - max(y_start, 0.0))
        v_bores += np.pi * h["r"] ** 2 * (cfg.hole_depth_mm - max(y_start, 0.0))
    v_body = v_outer - v_cavity + v_pillars - v_bores
    return {
        "wall_mm": wall,
        "outer_mm3": v_outer,
        "cavity_mm3": v_cavity,
        "pillars_mm3": v_pillars,
        "bores_mm3": v_bores,
        "body_mm3": v_body,
        "mass_g": v_body / 1000.0 * cfg.density_g_cm3,
    }


def wall_table(cfg, root3, tip3, holes, exact_body_mm3: float | None = None) -> list[dict]:
    walls = sorted(set(list(cfg.wall_table_mm) + [cfg.wall_thickness_mm]))
    rows = []
    for w in walls:
        try:
            row = shell_volume_2d(cfg, root3, tip3, holes, w)
        except Exception as e:  # noqa: BLE001
            row = {"wall_mm": w, "error": str(e)}
        row["configured"] = np.isclose(w, cfg.wall_thickness_mm)
        if row["configured"] and exact_body_mm3 is not None:
            row["exact_mass_g"] = exact_body_mm3 / 1000.0 * cfg.density_g_cm3
        rows.append(row)
    return rows


def build_report(b, exact: bool = True) -> dict:
    """Assemble all numbers for a WingBuild. exact=True computes OCCT triangulated properties."""
    cfg = b.cfg
    rep: dict = {"config": cfg.to_dict(), "checks": b.checks, "timings_s": b.timings}
    foil = b.foil
    xm, tm = foil.max_thickness()
    rep["airfoil"] = {
        "name": foil.name,
        "frame": foil.frame.describe() if foil.frame else "?",
        "te_cut_x_c": foil.x_te(),
        "te_gap_c": foil.te_gap(),
        "te_gap_root_mm": foil.te_gap() * cfg.root_chord_mm,
        "te_gap_tip_mm": foil.te_gap() * cfg.tip_chord_mm,
        "physical_root_length_mm": foil.x_te() * cfg.root_chord_mm,
        "physical_tip_length_mm": foil.x_te() * cfg.tip_chord_mm,
        "max_thickness_c": tm,
        "max_thickness_x_c": xm,
        "max_thickness_root_mm": tm * cfg.root_chord_mm,
        "max_thickness_tip_mm": tm * cfg.tip_chord_mm,
        "section_area_c2": foil.area(),
    }
    pf = cfg.planform()
    rep["planform"] = {
        "area_cm2": pf.planform_area() / 100.0,
        "taper": cfg.tip_chord_mm / cfg.root_chord_mm,
        "tip_le_offset_mm": pf.station(1).x_le,
        "bbox": geo.bbox(b.body),
    }
    rep["holes"] = [
        {k: (float(v) if isinstance(v, (np.floating, float)) else v) for k, v in h.items()} for h in b.holes
    ]
    if exact:
        v_body, a_body = geo.volume(b.body), geo.area(b.body)
        v_outer, a_outer = geo.volume(b.outer), geo.area(b.outer)
        rep["exact"] = {
            "body_volume_cm3": v_body / 1000,
            "body_area_cm2": a_body / 100,
            "outer_volume_cm3": v_outer / 1000,
            "wetted_area_cm2": a_outer / 100,
            "mass_g": v_body / 1000 * cfg.density_g_cm3,
            "solid_mass_g": v_outer / 1000 * cfg.density_g_cm3,
        }
    rep["wall_table"] = wall_table(
        cfg,
        b.root3,
        b.tip3,
        b.holes,
        rep.get("exact", {}).get("body_volume_cm3", None) and rep["exact"]["body_volume_cm3"] * 1000,
    )
    return rep


def format_report(rep: dict) -> str:
    cfg, a, p = rep["config"], rep["airfoil"], rep["planform"]
    L = []
    L.append("=" * 78)
    L.append(f"WINGTIP REPORT  ({a['name']}, {a['frame']})")
    L.append("=" * 78)
    L.append(
        f"planform : root {cfg['root_chord_mm']:g} mm, tip {cfg['tip_chord_mm']:g} mm, span {cfg['span_mm']:g} mm, "
        f"LE sweep {cfg['le_sweep_deg']:g}°, washout {cfg['washout_deg']:g}°, dihedral {cfg['dihedral_deg']:g}°"
    )
    L.append(
        f"           area {p['area_cm2']:.1f} cm², taper {p['taper']:.2f}, "
        f"tip LE {p['tip_le_offset_mm']:.1f} mm aft of root LE"
    )
    bb = p["bbox"]
    L.append(
        f"bbox     : x {bb['xmin']:.1f}..{bb['xmax']:.1f}  y {bb['ymin']:.1f}..{bb['ymax']:.1f}  "
        f"z {bb['zmin']:.1f}..{bb['zmax']:.1f} mm"
    )
    L.append(
        f"airfoil  : TE cut at {a['te_cut_x_c']:.3f} c -> physical length root {a['physical_root_length_mm']:.2f} mm, "
        f"tip {a['physical_tip_length_mm']:.2f} mm"
    )
    L.append(
        f"           TE thickness root {a['te_gap_root_mm']:.2f} mm, tip {a['te_gap_tip_mm']:.2f} mm  "
        f"({'!! thin for FDM; consider a larger te_truncate_pct' if a['te_gap_tip_mm'] < 0.8 else 'ok'})"
    )
    L.append(
        f"           max thickness {a['max_thickness_c'] * 100:.1f} % c at {a['max_thickness_x_c'] * 100:.0f} % c "
        f"-> {a['max_thickness_root_mm']:.1f} mm root, {a['max_thickness_tip_mm']:.1f} mm tip"
    )
    L.append(
        f"checks   : outer valid {rep['checks'].get('outer_valid')}, "
        f"cavity valid {rep['checks'].get('cavity_valid', '-')}, "
        f"body valid {rep['checks'].get('body_valid')}, loft-vs-Simpson {rep['checks'].get('simpson_rel_err', 0):.2%}"
    )
    L.append(
        f"holes    : (spanwise from the root face, depth {cfg['hole_depth_mm']:g} mm, "
        f"boss wall {cfg['boss_wall_mm']:g} mm, validated min wall {cfg['hole_min_wall_mm']:g} mm)"
    )
    for h in rep["holes"]:
        L.append(
            f"           {h['name']:>6}: {h['x_pct']:5.1f} % c -> x={h['x']:6.2f} z={h['z']:5.2f} mm, ⌀{h['d_mm']:g}, "
            f"min clearance {h['min_clearance']:+.2f} mm (at y={h['at_y']:.1f})"
        )
    if "exact" in rep:
        e = rep["exact"]
        L.append(
            f"exact    : body volume {e['body_volume_cm3']:.2f} cm³, surface {e['body_area_cm2']:.1f} cm², "
            f"wetted (outer) {e['wetted_area_cm2']:.1f} cm², solid-equivalent volume {e['outer_volume_cm3']:.1f} cm³"
        )
        L.append(
            f"MASS     : {e['mass_g']:.1f} g at wall {cfg['wall_thickness_mm']:g} mm, "
            f"TPU {cfg['density_g_cm3']:g} g/cm³ "
            f"(fully solid would be {e['solid_mass_g']:.0f} g)"
        )
    L.append("")
    L.append(f"wall-thickness trade (2D span integration; target ≤ {cfg['target_mass_g']:g} g):")
    L.append(f"  {'wall':>6} {'shell vol':>10} {'mass':>8}  {'':10} note")
    for r in rep["wall_table"]:
        if "error" in r:
            L.append(f"  {r['wall_mm']:6.2f}  ERROR: {r['error']}")
            continue
        flag = "  <= target" if r["mass_g"] <= cfg["target_mass_g"] else ""
        cfgmark = " <- configured" if r["configured"] else ""
        exact = f" (OCCT exact {r['exact_mass_g']:.1f} g)" if "exact_mass_g" in r else ""
        L.append(f"  {r['wall_mm']:6.2f} {r['body_mm3'] / 1000:8.1f} cm³ {r['mass_g']:7.1f} g{flag}{cfgmark}{exact}")
    L.append("")
    L.append("timings  : " + ", ".join(f"{k} {v:.1f}s" for k, v in rep["timings_s"].items()))
    return "\n".join(L)


def write_report(rep: dict, out_dir: str | Path, prefix: str = "wingtip") -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    txt = out_dir / "report.txt"
    js = out_dir / f"{prefix}_run.json"
    txt.write_text(format_report(rep) + "\n")

    def default(o):
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.bool_):
            return bool(o)
        return str(o)

    js.write_text(json.dumps(rep, indent=2, default=default))
    return txt, js
