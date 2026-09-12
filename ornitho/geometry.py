"""CadQuery / OCCT operations: wires from point arrays, lofts, booleans, export.

Everything here takes already-placed 3D point arrays (see sections.py); no
airfoil or planform logic lives in this module.
"""

from __future__ import annotations

from pathlib import Path

import cadquery as cq
import numpy as np
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections


def _vecs(pts3: np.ndarray) -> list[cq.Vector]:
    return [cq.Vector(float(x), float(y), float(z)) for x, y, z in pts3]


def outer_wire(pts3: np.ndarray, n_tail_lines: int = 0) -> cq.Wire:
    """One interpolating spline through an open outline + straight closing edge (blunt TE).

    n_tail_lines > 0: the last n points are sharp corners (Gurney tab) joined by lines
    instead of being part of the spline.
    """
    v = _vecs(pts3)
    k = len(v) - n_tail_lines
    edges = [cq.Edge.makeSpline(v[:k], periodic=False)]
    for i in range(k - 1, len(v) - 1):
        edges.append(cq.Edge.makeLine(v[i], v[i + 1]))
    edges.append(cq.Edge.makeLine(v[-1], v[0]))
    return cq.Wire.assembleEdges(edges)


def inner_wire(upper3: np.ndarray, lower3: np.ndarray, tol: float = 1e-6) -> cq.Wire:
    """Two splines (tail->nose along upper, nose->tail along lower) meeting at sharp vertices.

    If the tail points differ (flat inner TE) a closing line is added.
    """
    up = _vecs(upper3[::-1])  # tail -> nose
    lo = _vecs(lower3)  # nose -> tail
    lo[0] = up[-1]  # share the exact nose vertex
    edges = [cq.Edge.makeSpline(up, periodic=False), cq.Edge.makeSpline(lo, periodic=False)]
    if (lo[-1] - up[0]).Length > tol:
        edges.append(cq.Edge.makeLine(lo[-1], up[0]))
    return cq.Wire.assembleEdges(edges)


def loft(wires: list[cq.Wire], ruled: bool = True) -> cq.Solid:
    """Solid loft with OCCT's wire-compatibility pass DISABLED.

    Our wires are built with identical edge count, start vertex and direction,
    so ordered matching is exact; the default compatibility pass may re-pick a
    start vertex near a blunt TE and produce a twisted, self-intersecting loft.
    """
    b = BRepOffsetAPI_ThruSections(True, ruled)
    b.CheckCompatibility(False)
    for w in wires:
        b.AddWire(w.wrapped)
    b.Build()
    if not b.IsDone():
        raise RuntimeError("loft failed (ThruSections not done)")
    s = cq.Shape.cast(b.Shape())
    if not s.isValid():
        raise RuntimeError("loft produced an invalid shape")
    return s


def extrude(wire: cq.Wire, vec: tuple[float, float, float]) -> cq.Solid:
    return cq.Solid.extrudeLinear(wire, [], cq.Vector(*vec))


def cylinder_y(cx: float, cz: float, r: float, y0: float, y1: float) -> cq.Solid:
    """Cylinder along +y from y0 to y1 centred at (cx, cz)."""
    return cq.Solid.makeCylinder(r, y1 - y0, cq.Vector(cx, y0, cz), cq.Vector(0, 1, 0))


def export(
    shape: cq.Shape,
    step_path: str | Path | None,
    stl_path: str | Path | None,
    stl_tol: float = 0.02,
    stl_ang: float = 0.1,
) -> None:
    if step_path:
        Path(step_path).parent.mkdir(parents=True, exist_ok=True)
        shape.exportStep(str(step_path))
    if stl_path:
        Path(stl_path).parent.mkdir(parents=True, exist_ok=True)
        shape.exportStl(str(stl_path), tolerance=stl_tol, angularTolerance=stl_ang, ascii=False, relative=False)


def tessellate(shape: cq.Shape, tol: float = 0.05, ang: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    verts, tris = shape.tessellate(tol, ang)
    return np.array([v.toTuple() for v in verts]), np.array(tris, dtype=np.int64)


def bbox(shape: cq.Shape) -> dict[str, float]:
    b = shape.BoundingBox()
    return {
        "xmin": b.xmin,
        "xmax": b.xmax,
        "ymin": b.ymin,
        "ymax": b.ymax,
        "zmin": b.zmin,
        "zmax": b.zmax,
        "xlen": b.xlen,
        "ylen": b.ylen,
        "zlen": b.zlen,
    }


# --------------------------------------------------------------------------- #
# Mass properties
# --------------------------------------------------------------------------- #
# OCCT's analytic Gauss integration (Shape.Volume()) is unreliable on solids
# bounded by many-span interpolating B-spline faces (observed -25 % on an
# S1223 prism, and inconsistent across tolerances). Integrating over a fine
# triangulation is deterministic and matches analytic values to ~0.02 %.
def _triangulate(shape: cq.Shape, lin: float) -> None:
    from OCP.BRepMesh import BRepMesh_IncrementalMesh

    BRepMesh_IncrementalMesh(shape.wrapped, lin, False, 0.1, True)


def volume(shape: cq.Shape, lin: float = 0.005) -> float:
    """Volume in mm³ from a fine triangulation."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    _triangulate(shape, lin)
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, p, True, False, True)
    return abs(p.Mass())


def area(shape: cq.Shape, lin: float = 0.005) -> float:
    """Surface area in mm² from a fine triangulation."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    _triangulate(shape, lin)
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape.wrapped, p, True, False)
    return p.Mass()


def step_roundtrip_volume(step_path: str | Path) -> float:  # noqa: F811 (replaces the naive version)
    return volume(cq.importers.importStep(str(step_path)).val())
