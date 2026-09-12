"""Real OCCT build of the default wingtip. Run with: pytest -m slow"""

import numpy as np
import pytest

from ornitho import geometry as geo
from ornitho import report, wing
from ornitho.config import WingConfig

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def build():
    return wing.build(WingConfig())


def test_solids_valid_and_loft_matches_simpson(build):
    assert build.checks["outer_valid"] and build.checks["cavity_valid"] and build.checks["body_valid"]
    assert build.checks["simpson_rel_err"] < 0.005


def test_hollow_volume_matches_2d_integration(build):
    v_exact = geo.volume(build.body)
    est = report.shell_volume_2d(build.cfg, build.root3, build.tip3, build.holes, build.cfg.wall_thickness_mm)
    assert abs(v_exact - est["body_mm3"]) / v_exact < 0.01
    assert v_exact < geo.volume(build.outer) * 0.6  # it really is hollow


def test_tessellation_watertight(build):
    import pyvista as pv

    verts, tris = geo.tessellate(build.body)
    m = pv.PolyData(verts, np.hstack([np.full((len(tris), 1), 3), tris]).ravel()).clean(tolerance=1e-7)
    assert m.n_open_edges == 0
    assert abs(m.volume - geo.volume(build.body)) / m.volume < 0.005


def test_step_roundtrip(build, tmp_path):
    geo.export(build.body, tmp_path / "w.step", tmp_path / "w.stl")
    v = geo.step_roundtrip_volume(tmp_path / "w.step")
    assert abs(v - geo.volume(build.body)) / v < 0.001
    assert (tmp_path / "w.stl").stat().st_size > 100_000


def test_bounding_box(build):
    bb = geo.bbox(build.body)
    cfg = build.cfg
    assert bb["ymin"] == pytest.approx(0.0, abs=0.2) and bb["ymax"] == pytest.approx(cfg.span_mm, abs=0.2)
    x_tip_te = cfg.span_mm * np.tan(np.radians(cfg.le_sweep_deg)) + 0.99 * cfg.tip_chord_mm
    assert bb["xmax"] == pytest.approx(max(0.99 * cfg.root_chord_mm, x_tip_te), abs=0.2)
    assert bb["zmin"] < -3  # tip LE droops with 8 deg washout


def test_gurney_variant_builds(build):
    b = wing.build(WingConfig(gurney_flap_pct=1.5, gurney_thickness_mm=1.2), hollow=True, holes=True)
    assert b.checks["body_valid"]
    # the tab adds material: ~1.2 mm x 2.5 mm x 270 mm (tapering) -> a few hundred mm3
    extra = geo.volume(b.outer) - geo.volume(build.outer)
    assert 300 < extra < 2000
    # the tab drops 1.5 % of the root chord below its attachment point on the lower surface
    assert b.root3[-3, 2] - b.root3[-2, 2] == pytest.approx(0.015 * 165, abs=1e-6)
    assert b.root3[-1, 0] == pytest.approx(build.root3[-1, 0], abs=1e-6)  # aft face at the TE cut
