"""Assemble the wingtip: airfoil -> placed sections -> lofts -> hollow -> bosses/holes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from . import airfoil as af
from . import geometry as geo
from . import sections as sec
from . import validate
from .config import WingConfig


@dataclass
class WingBuild:
    cfg: WingConfig
    foil: af.Airfoil  # root-station airfoil
    root3: np.ndarray
    tip3: np.ndarray
    outer: object  # cq.Solid
    body: object  # cq.Solid (hollow + holes)
    holes: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    tip_foil: af.Airfoil | None = None

    def overlays(self) -> dict[str, np.ndarray]:
        pf = self.cfg.planform()
        return {
            "root outline": np.vstack([self.root3, self.root3[:1]]),
            "tip outline": np.vstack([self.tip3, self.tip3[:1]]),
            "quarter chord": pf.quarter_chord_line(),
        }


def load_airfoil(cfg: WingConfig, chord_mm: float | None = None) -> af.Airfoil:
    """Processed airfoil for a station of the given chord (Gurney tab thickness is absolute)."""
    path = cfg.airfoil_path()
    if not str(path).endswith(".dat"):
        path = af.fetch(str(path))
    chord = cfg.root_chord_mm if chord_mm is None else chord_mm
    return af.load(
        path,
        te_truncate_pct=cfg.te_truncate_pct,
        n_per_surface=cfg.n_per_surface,
        gurney_pct=cfg.gurney_flap_pct,
        gurney_thickness=cfg.gurney_thickness_mm / chord,
    )


def placed_sections(cfg: WingConfig, root_foil: af.Airfoil, tip_foil: af.Airfoil) -> tuple[np.ndarray, np.ndarray]:
    pf = cfg.planform()
    return pf.station(0.0).place_unit(root_foil.outline()), pf.station(1.0).place_unit(tip_foil.outline())


def _inner_wire_at(cfg: WingConfig, f: float, t: float):
    st = cfg.planform().station(f)
    foil = load_airfoil(cfg, st.chord)
    upper, lower = sec.inset(foil.outline() * st.chord, t, cfg.n_inner)
    if np.linalg.norm(upper[-1] - lower[-1]) > 1e-6:
        raise RuntimeError("inner contour has a flat tail (TE thicker than 2*wall); unsupported")
    return geo.inner_wire(st.place_mm(upper), st.place_mm(lower))


def build(cfg: WingConfig, hollow: bool = True, holes: bool = True, wall: float | None = None) -> WingBuild:
    """Build the wingtip solid. wall overrides cfg.wall_thickness_mm (for the mass table)."""
    t = cfg.wall_thickness_mm if wall is None else wall
    tm: dict[str, float] = {}
    t0 = time.perf_counter()

    foil = load_airfoil(cfg, cfg.root_chord_mm)
    tip_foil = load_airfoil(cfg, cfg.tip_chord_mm)
    root3, tip3 = placed_sections(cfg, foil, tip_foil)
    hole_info = validate.check_holes(cfg, foil, root3, tip3) if holes else []
    tm["airfoil+validate"] = time.perf_counter() - t0

    t1 = time.perf_counter()
    outer = geo.loft([geo.outer_wire(root3, foil.n_corners), geo.outer_wire(tip3, tip_foil.n_corners)], ruled=True)
    v_outer = geo.volume(outer)
    v_simpson = validate.simpson_volume(root3, tip3, cfg.span_mm)
    rel = abs(v_outer - v_simpson) / v_simpson
    if rel > 0.005:
        raise RuntimeError(f"outer loft volume {v_outer:.0f} differs from Simpson {v_simpson:.0f} by {rel:.1%}")
    tm["outer loft"] = time.perf_counter() - t1
    checks = {
        "outer_valid": outer.isValid(),
        "outer_volume_mm3": v_outer,
        "simpson_volume_mm3": v_simpson,
        "simpson_rel_err": rel,
    }

    body = outer
    y_start = -1.0 if cfg.root_solid_mm <= 0 else cfg.root_solid_mm
    if hollow:
        t2 = time.perf_counter()
        f0, f1 = y_start / cfg.span_mm, (cfg.span_mm - t) / cfg.span_mm
        cavity = geo.loft([_inner_wire_at(cfg, f0, t), _inner_wire_at(cfg, f1, t)], ruled=True)
        checks["cavity_valid"] = cavity.isValid()
        if holes:
            pillars = [geo.cylinder_y(h["x"], h["z"], h["r_boss"], y_start, cfg.hole_depth_mm + t) for h in hole_info]
            cavity = cavity.cut(*pillars)
        body = outer.cut(cavity)
        tm["hollow"] = time.perf_counter() - t2
    if holes:
        t3 = time.perf_counter()
        bores = [geo.cylinder_y(h["x"], h["z"], h["r"], y_start, cfg.hole_depth_mm) for h in hole_info]
        body = body.cut(*bores)
        tm["holes"] = time.perf_counter() - t3
    checks["body_valid"] = body.isValid()
    if not body.isValid():
        raise RuntimeError("final body is not a valid solid")
    tm["total"] = time.perf_counter() - t0
    return WingBuild(cfg, foil, root3, tip3, outer, body, hole_info, checks, tm, tip_foil)
