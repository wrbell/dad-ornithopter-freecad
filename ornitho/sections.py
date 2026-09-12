"""Span-station math and 2D section operations. Pure numpy + shapely (no OCCT).

Coordinate frame (global, mm):
    x  chordwise, positive aft; root LE at x = 0
    y  spanwise, positive outboard; root (rib face) at y = 0
    z  up
A section at span fraction f = y / span is placed by: scale to chord(f) ->
rotate about its quarter-chord point by twist(f) (nose-down positive) ->
translate to (x_le(f), y, z_dihedral(f)). Sections therefore stay in planes
y = const, and a ruled loft between root and tip realises exactly
section_at(f) = (1 - f) * root + f * tip.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.polygon import orient


@dataclass(frozen=True)
class Planform:
    root_chord: float
    tip_chord: float
    span: float
    le_sweep_deg: float = 0.0
    washout_deg: float = 0.0
    dihedral_deg: float = 0.0

    def station(self, f: float) -> "Station":
        return Station(
            f=f,
            y=f * self.span,
            chord=self.root_chord + f * (self.tip_chord - self.root_chord),
            x_le=f * self.span * np.tan(np.radians(self.le_sweep_deg)),
            twist_deg=f * self.washout_deg,
            z_dih=f * self.span * np.tan(np.radians(self.dihedral_deg)),
        )

    def quarter_chord_line(self) -> np.ndarray:
        r, t = self.station(0.0), self.station(1.0)
        return np.array([[r.x_le + 0.25 * r.chord, r.y, r.z_dih], [t.x_le + 0.25 * t.chord, t.y, t.z_dih]])

    def planform_area(self) -> float:
        return 0.5 * (self.root_chord + self.tip_chord) * self.span


@dataclass(frozen=True)
class Station:
    f: float
    y: float
    chord: float
    x_le: float
    twist_deg: float
    z_dih: float

    def place_mm(self, pts_mm: np.ndarray) -> np.ndarray:
        """Local section points (N,2) in mm, LE at (0,0), chord along +x -> global (N,3)."""
        a = np.radians(self.twist_deg)
        xr = pts_mm[:, 0] - 0.25 * self.chord
        zr = pts_mm[:, 1]
        X = self.x_le + 0.25 * self.chord + xr * np.cos(a) - zr * np.sin(a)
        Z = self.z_dih + xr * np.sin(a) + zr * np.cos(a)
        Y = np.full_like(X, self.y)
        return np.column_stack([X, Y, Z])

    def place_unit(self, pts_unit: np.ndarray) -> np.ndarray:
        return self.place_mm(np.asarray(pts_unit) * self.chord)


def section_at(root3: np.ndarray, tip3: np.ndarray, f: float) -> np.ndarray:
    """Cross-section of the ruled loft at span fraction f (N,3); same point order as root/tip."""
    return (1.0 - f) * root3 + f * tip3


def polygon_xz(pts3: np.ndarray) -> Polygon:
    """Shapely polygon of a section from its x and z columns."""
    return Polygon(pts3[:, [0, 2]])


def area_xz(pts3: np.ndarray) -> float:
    return polygon_xz(pts3).area


def _resample(poly: np.ndarray, n: int) -> np.ndarray:
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    s /= s[-1]
    t = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n)))
    return np.column_stack([np.interp(t, s, poly[:, 0]), np.interp(t, s, poly[:, 1])])


def inset(outline_mm: np.ndarray, t: float, n: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """Erode a closed 2D section (mm) by wall thickness t.

    Returns (upper, lower), each (n,2) running nose -> tail along the eroded
    contour. Where the section is thinner than 2t (aft region) the contour
    collapses to a sharp tail cusp, so upper[-1] == lower[-1] there.
    Raises ValueError if the wall swallows the whole section.
    """
    poly = Polygon(outline_mm)
    if not poly.is_valid:
        poly = poly.buffer(0)
    er = poly.buffer(-t, join_style="mitre", mitre_limit=2.0)
    if isinstance(er, MultiPolygon):
        er = max(er.geoms, key=lambda g: g.area)
    if er.is_empty or er.area < 4.0:
        raise ValueError(f"wall thickness {t} mm leaves no cavity (section area {poly.area:.1f} mm²)")
    ring = np.asarray(orient(er, sign=1.0).exterior.coords)[:-1]  # CCW, unique vertices
    i_nose = int(np.argmin(ring[:, 0]))
    ring = np.roll(ring, -i_nose, axis=0)  # start at the nose
    i_tail = int(np.argmax(ring[:, 0]))
    # CCW from the nose: first the lower surface (nose -> tail), then upper (tail -> nose).
    lower = ring[: i_tail + 1]
    upper = np.vstack([ring[i_tail:], ring[:1]])[::-1]  # nose -> tail
    return _resample(upper, n), _resample(lower, n)


def inner_outline(upper: np.ndarray, lower: np.ndarray) -> np.ndarray:
    """tail_upper -> upper -> nose -> lower -> tail_lower (mirrors Airfoil.outline())."""
    return np.vstack([upper[::-1], lower[1:]])


def circle_inside(poly: Polygon, cx: float, cz: float, r: float) -> tuple[bool, float]:
    """(inside?, clearance) for a circle: clearance = distance from centre to boundary minus r."""
    p = Point(cx, cz)
    d = poly.exterior.distance(p)
    inside = poly.contains(p) and d >= r
    return inside, d - r
