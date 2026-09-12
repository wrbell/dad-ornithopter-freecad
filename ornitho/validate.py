"""Pre-flight geometric checks that must pass before any OCCT work starts."""

from __future__ import annotations

import numpy as np

from .sections import circle_inside, polygon_xz, section_at


class HoleValidationError(ValueError):
    pass


def hole_centres(cfg, foil) -> list[dict]:
    """Global (x, z) of each hole centre in the root plane, plus radii."""
    out = []
    for h in cfg.mount_holes:
        x = h.x_pct / 100.0 * cfg.root_chord_mm
        if h.z_pct is None:
            z = float(foil.camber(h.x_pct / 100.0)) * cfg.root_chord_mm
        else:
            z = h.z_pct / 100.0 * cfg.root_chord_mm
        out.append(
            {
                "name": h.name,
                "x": x,
                "z": z,
                "r": h.d_mm / 2.0,
                "r_boss": h.d_mm / 2.0 + cfg.boss_wall_mm,
                "r_check": h.d_mm / 2.0 + cfg.hole_min_wall_mm,
                "x_pct": h.x_pct,
                "d_mm": h.d_mm,
            }
        )
    return out


def check_holes(cfg, foil, root3: np.ndarray, tip3: np.ndarray, n_stations: int = 7) -> list[dict]:
    """Every hole, padded by hole_min_wall_mm, must sit inside the section at every
    station it passes through (the section shrinks, sweeps and twists over the depth).

    Returns per-hole dicts with the minimum clearance (padded hole edge to skin) and
    where it occurs. Raises HoleValidationError naming the offending hole.
    """
    holes = hole_centres(cfg, foil)
    depth = cfg.hole_depth_mm + cfg.wall_thickness_mm
    fs = np.linspace(0.0, min(1.0, depth / cfg.span_mm), n_stations)
    problems = []
    for h in holes:
        h["min_clearance"] = np.inf
        h["at_y"] = 0.0
        for f in fs:
            poly = polygon_xz(section_at(root3, tip3, f))
            inside, clearance = circle_inside(poly, h["x"], h["z"], h["r_check"])
            if clearance < h["min_clearance"]:
                h["min_clearance"], h["at_y"] = float(clearance), float(f * cfg.span_mm)
            if not inside:
                problems.append(
                    f"hole '{h['name']}' ({h['x_pct']:.1f} % c, d={h['d_mm']:g} mm + {cfg.hole_min_wall_mm:g} mm wall) "
                    f"breaches the section at y={f * cfg.span_mm:.1f} mm: clearance {clearance:+.2f} mm"
                )
                break
    for i in range(len(holes)):
        for j in range(i + 1, len(holes)):
            a, b = holes[i], holes[j]
            gap = np.hypot(a["x"] - b["x"], a["z"] - b["z"]) - a["r_check"] - b["r_check"]
            if gap < 0:
                problems.append(
                    f"holes '{a['name']}' and '{b['name']}' are too close (overlap {-gap:.2f} mm incl. min wall)"
                )
    if problems:
        raise HoleValidationError("mount hole validation failed:\n  " + "\n  ".join(problems))
    return holes


def simpson_volume(root3: np.ndarray, tip3: np.ndarray, span: float) -> float:
    """Exact volume of the ruled loft between two sections (area is quadratic in f)."""
    from .sections import area_xz

    a0, am, a1 = (area_xz(section_at(root3, tip3, f)) for f in (0.0, 0.5, 1.0))
    return span * (a0 + 4 * am + a1) / 6.0
