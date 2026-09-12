"""Rendering: 2D diagnostic plots (matplotlib) and 3D views (pyvista, matplotlib fallback)."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")


def plot_airfoil(
    airfoil,
    path: str | Path,
    raw_loop: np.ndarray | None = None,
    chord_mm: float | None = None,
    title: str | None = None,
) -> Path:
    """Unit-chord section plot: processed outline (and the raw file points if given)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(12, 7.5), gridspec_kw={"height_ratios": [3, 1.6]})
    o = airfoil.polygon()
    if raw_loop is not None:
        ax.plot(raw_loop[:, 0], raw_loop[:, 1], "o", ms=3, color="0.6", label=f"raw file points ({len(raw_loop)})")
    ax.plot(o[:, 0], o[:, 1], "-", color="C0", lw=1.5, label=f"processed outline ({len(o) - 1} pts)")
    ax.plot(airfoil.upper[:, 0], airfoil.upper[:, 1], ".", ms=3, color="C3", label="upper (resampled)")
    ax.plot(airfoil.lower[:, 0], airfoil.lower[:, 1], ".", ms=3, color="C2", label="lower (resampled)")
    xs = np.linspace(0, airfoil.x_te(), 200)
    ax.plot(xs, airfoil.camber(xs), "--", color="0.3", lw=0.8, label="camber (mid-thickness)")
    ax.axhline(0, color="0.8", lw=0.5)
    ax.set_aspect("equal")
    ax.set_xlim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)
    xm, tm = airfoil.max_thickness()
    info = (
        f"{airfoil.name}: x_te={airfoil.x_te():.3f}, TE gap={airfoil.te_gap():.4f} c, "
        f"max t={tm:.4f} c @ x={xm:.3f}, area={airfoil.area():.5f} c²"
    )
    if chord_mm:
        info += f"  |  at {chord_mm:g} mm: TE gap {airfoil.te_gap() * chord_mm:.2f} mm, max t {tm * chord_mm:.1f} mm"
    ax.set_title(title or info, fontsize=10)
    ax.set_xlabel("x / c")
    ax.set_ylabel("y / c")
    # TE close-up
    ax2.plot(o[:, 0], o[:, 1], "-", color="C0", lw=1.5)
    ax2.plot(airfoil.upper[:, 0], airfoil.upper[:, 1], ".", ms=4, color="C3")
    ax2.plot(airfoil.lower[:, 0], airfoil.lower[:, 1], ".", ms=4, color="C2")
    if raw_loop is not None:
        ax2.plot(raw_loop[:, 0], raw_loop[:, 1], "o", ms=4, color="0.6", mfc="none")
    ax2.set_xlim(0.9, 1.005)
    ax2.set_ylim(-0.01, 0.06)
    ax2.set_aspect("equal")
    ax2.grid(True, alpha=0.3)
    ax2.set_title("trailing-edge close-up (blunt cut should be a vertical segment)", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- #
# 3D views
# --------------------------------------------------------------------------- #
VIEW_NOTES = {
    "top": "planform, looking down -z: LE at top, span to the right",
    "front": "looking aft along +x from the nose: tip on the left",
    "side": "looking inboard along -y from the tip: nose to the right, washout visible",
    "root": "looking outboard along +y at the root face (y=0)",
    "iso": "perspective from ahead/above/outboard",
    "iso_root": "perspective from behind the root face: open root, cavity, pillars",
}


def _views(center, D):
    c = np.asarray(center)
    return {
        "top": (c + [0, 0, 3 * D], (-1, 0, 0), True),
        "front": (c + [-3 * D, 0, 0], (0, 0, 1), True),
        "side": (c + [0, 3 * D, 0], (0, 0, 1), True),
        "root": (c + [0, -3 * D, 0], (0, 0, 1), True),
        "iso": (c + D * np.array([-1.2, 1.4, 0.9]), (0, 0, 1), False),
        "iso_root": (c + D * np.array([-0.35, -1.5, 0.45]), (0, 0, 1), False),
    }


def render_views(
    verts: np.ndarray,
    tris: np.ndarray,
    out_dir: str | Path,
    prefix: str = "wingtip",
    overlays: dict[str, np.ndarray] | None = None,
    title: str = "",
    views: list[str] | None = None,
    size=(1600, 1000),
    overlay_views: tuple[str, ...] = ("top",),
) -> list[Path]:
    """Render named views of a triangle mesh to PNG. pyvista first, matplotlib fallback."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    views = views or list(VIEW_NOTES)
    try:
        return _render_pyvista(verts, tris, out_dir, prefix, overlays or {}, title, views, size, overlay_views)
    except Exception as e:  # noqa: BLE001
        print(f"[render] pyvista failed ({type(e).__name__}: {e}); falling back to matplotlib")
        return _render_mpl(verts, tris, out_dir, prefix, overlays or {}, title, views)


def _render_pyvista(verts, tris, out_dir, prefix, overlays, title, views, size, overlay_views):
    import pyvista as pv

    faces = np.hstack([np.full((len(tris), 1), 3, dtype=np.int64), tris]).ravel()
    mesh = pv.PolyData(verts, faces).clean(tolerance=1e-7)  # merge per-face duplicate vertices
    if mesh.n_open_edges:
        print(f"[render] WARNING: tessellation has {mesh.n_open_edges} open edges (not watertight)")
    center, D = np.array(mesh.center), mesh.length
    lo, hi = np.array(mesh.bounds[0::2]), np.array(mesh.bounds[1::2])
    ext = hi - lo
    aspect = size[0] / size[1]
    # visible (horizontal, vertical) extents per parallel view, for an explicit fit
    extents = {"top": (ext[1], ext[0]), "front": (ext[1], ext[2]), "side": (ext[0], ext[2]), "root": (ext[0], ext[2])}
    paths = []
    for name in views:
        pos, up, parallel = _views(center, D)[name]
        pl = pv.Plotter(off_screen=True, window_size=list(size))
        pl.set_background("white")
        # split_sharp_edges: smooth shading without vertex-normal smearing across silhouettes
        pl.add_mesh(
            mesh, color="lightsteelblue", smooth_shading=True, split_sharp_edges=True, feature_angle=20, specular=0.3
        )
        if name in overlay_views:
            for oname, pts in overlays.items():
                pts = np.asarray(pts, float).copy()
                if name == "top":
                    pts[:, 2] = hi[2] + 1.0  # lift above the surface so lines are not buried
                col = "red" if "quarter" in oname else ("black" if "root" in oname else "darkgreen")
                pl.add_mesh(pv.lines_from_points(pts, close=False), color=col, line_width=3)
        pl.add_axes(xlabel="x aft", ylabel="y span", zlabel="z up")
        try:
            pl.show_bounds(
                xtitle="x aft (mm)",
                ytitle="y span (mm)",
                ztitle="z up (mm)",
                font_size=6,
                color="black",
                grid=False,
                location="outer",
                n_xlabels=5,
                n_ylabels=5,
                n_zlabels=2,
                use_3d_text=False,
            )
        except TypeError:  # older pyvista
            pl.show_bounds(
                xtitle="x aft (mm)",
                ytitle="y span (mm)",
                ztitle="z up (mm)",
                font_size=10,
                color="black",
                grid=False,
                location="outer",
            )
        pl.add_text(f"{name.upper()} — {VIEW_NOTES[name]}\n{title}", font_size=11, color="black")
        pl.camera_position = [tuple(pos), tuple(center), up]
        if parallel:
            pl.enable_parallel_projection()
            w, h = extents[name]
            pl.camera.parallel_scale = 0.62 * max(h, w / aspect)  # fit with margin for axis labels
        else:
            pl.reset_camera()
        p = out_dir / f"{prefix}_{name}.png"
        pl.screenshot(str(p))
        pl.close()
        paths.append(p)
    return paths


def _render_mpl(verts, tris, out_dir, prefix, overlays, title, views):
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    angles = {"top": (90, -90), "front": (0, 180), "side": (0, 90), "root": (0, -90), "iso": (25, 135)}
    lo, hi = verts.min(0), verts.max(0)
    paths = []
    for name in views:
        fig = plt.figure(figsize=(12, 7.5))
        ax = fig.add_subplot(111, projection="3d")
        pc = Poly3DCollection(
            verts[tris],
            facecolor="lightsteelblue",
            edgecolor="none",
            shade=True,
            lightsource=matplotlib.colors.LightSource(azdeg=225, altdeg=45),
        )
        ax.add_collection3d(pc)
        for oname, pts in overlays.items():
            pts = np.asarray(pts)
            ax.plot(pts[:, 0], pts[:, 1], pts[:, 2], color="red" if "quarter" in oname else "black", lw=2)
        ax.set_xlim(lo[0], hi[0])
        ax.set_ylim(lo[1], hi[1])
        ax.set_zlim(lo[2], hi[2])
        ax.set_box_aspect(hi - lo)
        ax.set_proj_type("ortho" if name != "iso" else "persp")
        ax.view_init(*angles[name])
        ax.set_xlabel("x aft (mm)")
        ax.set_ylabel("y span (mm)")
        ax.set_zlabel("z up (mm)")
        ax.set_title(f"{name.upper()} — {VIEW_NOTES[name]}\n{title}", fontsize=10)
        p = out_dir / f"{prefix}_{name}.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        paths.append(p)
    return paths


# --------------------------------------------------------------------------- #
# 2D diagnostics for the wing
# --------------------------------------------------------------------------- #
def plot_planform(cfg, holes: list[dict], path: str | Path) -> Path:
    """Top-down planform: LE, TE, quarter-chord, tip, hole positions and depths."""
    pf = cfg.planform()
    r, t = pf.station(0), pf.station(1)
    x_te_r, x_te_t = r.x_le + 0.99 * r.chord, t.x_le + 0.99 * t.chord  # nominal; TE cut drawn by geometry
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.plot([0, cfg.span_mm], [r.x_le, t.x_le], "k-", lw=2, label=f"LE (sweep {cfg.le_sweep_deg:g}°)")
    ax.plot([0, cfg.span_mm], [x_te_r, x_te_t], "k-", lw=2, label="TE")
    ax.plot([0, 0], [r.x_le, x_te_r], "-", color="C3", lw=2, label=f"root {cfg.root_chord_mm:g} mm (rib face)")
    ax.plot([cfg.span_mm] * 2, [t.x_le, x_te_t], "-", color="C2", lw=2, label=f"tip {cfg.tip_chord_mm:g} mm")
    qc = pf.quarter_chord_line()
    ax.plot(qc[:, 1], qc[:, 0], "--", color="red", lw=1, label="quarter chord (twist axis)")
    for h in holes:
        ax.plot([0, cfg.hole_depth_mm], [h["x"], h["x"]], "-", color="C1", lw=3, alpha=0.7)
        ax.add_patch(
            plt.Rectangle(
                (0, h["x"] - h["r_boss"]),
                cfg.hole_depth_mm + cfg.wall_thickness_mm,
                2 * h["r_boss"],
                fc="C1",
                alpha=0.25,
                ec="none",
            )
        )
        ax.annotate(
            f"{h['name']} {h['x_pct']:g}% ⌀{h['d_mm']:g}", (cfg.hole_depth_mm + 3, h["x"]), fontsize=8, va="center"
        )
    ax.set_xlim(-10, cfg.span_mm + 10)
    ax.set_ylim(x_te_r + 10, -10)  # x aft points DOWN like the 3D top view
    ax.set_aspect("equal")
    ax.set_xlabel("y span (mm)")
    ax.set_ylabel("x aft (mm)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title(
        f"planform — area {pf.planform_area() / 100:.1f} cm², taper {cfg.tip_chord_mm / cfg.root_chord_mm:.2f}, "
        f"washout {cfg.washout_deg:g}°, dihedral {cfg.dihedral_deg:g}°",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return Path(path)


def plot_sections(cfg, foil, root3, tip3, holes: list[dict], path: str | Path, wall: float, tip_foil=None) -> Path:
    """Root and tip sections at true scale with inner contours, holes and bosses; plus washout panel."""
    from .sections import inner_outline, inset

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), gridspec_kw={"height_ratios": [1.2, 1]})
    tip_foil = tip_foil or foil
    # panel 1: root section, true mm, with cavity and holes
    root_mm = foil.outline() * cfg.root_chord_mm
    ax1.plot(root_mm[:, 0], root_mm[:, 1], "-", color="C3", lw=1.5, label=f"root outer ({cfg.root_chord_mm:g} mm)")
    try:
        u, lo = inset(root_mm, wall)
        inner = inner_outline(u, lo)
        ax1.plot(inner[:, 0], inner[:, 1], "-", color="C0", lw=1, label=f"root cavity (wall {wall:g} mm)")
    except ValueError as e:
        ax1.text(0.5, 0.5, str(e), transform=ax1.transAxes)
    tip_mm = tip_foil.outline() * cfg.tip_chord_mm
    ax1.plot(
        tip_mm[:, 0], tip_mm[:, 1], "-", color="C2", lw=1.2, label=f"tip outer ({cfg.tip_chord_mm:g} mm, LE aligned)"
    )
    try:
        u, lo = inset(tip_mm, wall)
        inner = inner_outline(u, lo)
        ax1.plot(inner[:, 0], inner[:, 1], "-", color="C0", lw=0.8)
    except ValueError as e:
        ax1.text(0.5, 0.4, str(e), transform=ax1.transAxes)
    for h in holes:
        ax1.add_patch(plt.Circle((h["x"], h["z"]), h["r_boss"], fc="C1", alpha=0.3, ec="none"))
        ax1.add_patch(plt.Circle((h["x"], h["z"]), h["r"], fc="white", ec="k", lw=1))
        ax1.annotate(
            f"{h['name']}\n{h['min_clearance']:+.1f} mm", (h["x"], h["z"] + h["r_boss"] + 1), fontsize=8, ha="center"
        )
    ax1.set_aspect("equal")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right", fontsize=8)
    ax1.set_xlabel("x from LE (mm)")
    ax1.set_ylabel("z (mm)")
    ax1.set_title(
        "sections in their own frame (untwisted): outer skin, cavity, holes (⌀) with boss (orange), "
        "annotated min clearance",
        fontsize=9,
    )
    # panel 2: placed root and tip in the global x-z plane (washout + sweep visible)
    for pts3, lab, col in ((root3, "root (y=0)", "C3"), (tip3, f"tip (y={cfg.span_mm:g})", "C2")):
        closed = np.vstack([pts3, pts3[:1]])
        ax2.plot(closed[:, 0], closed[:, 2], "-", color=col, lw=1.5, label=lab)
    qc = cfg.planform().quarter_chord_line()
    ax2.plot(qc[:, 0], qc[:, 2], "r+", ms=10, mew=2, label="quarter-chord points")
    ax2.set_aspect("equal")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper right", fontsize=8)
    ax2.set_xlabel("x aft (mm)")
    ax2.set_ylabel("z up (mm)")
    ax2.set_title(
        f"placed sections (global x–z): sweep {cfg.le_sweep_deg:g}°, washout {cfg.washout_deg:g}° "
        f"nose-down at tip, dihedral {cfg.dihedral_deg:g}°",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return Path(path)
