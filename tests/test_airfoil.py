import numpy as np
import pytest

from ornitho import airfoil as af
from tests.conftest import naca4, selig_loop

FORMATS = ["selig", "selig_reversed", "selig_le_start", "selig_closed", "lednicer",
           "lednicer_nocount", "three_col", "three_col_mm", "crlf_blank", "rotated"]


@pytest.mark.parametrize("fmt_name", FORMATS)
def test_all_formats_normalize_to_same_surfaces(naca2412, dat_writer, fmt_name):
    upper0, lower0 = naca2412
    path = dat_writer(upper0, lower0, fmt_name)
    loop = af.parse_dat(path)
    upper, lower, frame = af.normalize(loop)
    assert upper.shape == upper0.shape and lower.shape == lower0.shape
    tol = 3e-4 if fmt_name == "rotated" else 2e-6  # refit picks the geometric LE; others are exact
    assert np.abs(upper - upper0).max() < tol, fmt_name
    assert np.abs(lower - lower0).max() < tol, fmt_name
    expected_mode = {"three_col_mm": "scaled", "rotated": "refit"}.get(fmt_name, "native")
    assert frame.mode == expected_mode


def test_native_frame_is_kept_exactly_for_stock_s1223():
    path = af.fetch("s1223")
    raw = af.parse_dat(path)
    upper, lower, frame = af.normalize(raw)
    assert frame.mode == "native" and not frame.blunt_te
    pts = np.vstack([upper, lower])
    dev = np.abs(pts[:, None, :] - raw[None, :, :]).sum(-1).min(1)
    assert dev.max() < 1e-12
    assert upper[:, 1].mean() > lower[:, 1].mean()
    assert np.allclose(upper[-1], [1, 0]) and np.allclose(lower[-1], [1, 0])


def test_blunt_te_preserved(naca2412, dat_writer):
    upper, lower = naca4("2412", closed_te=False)
    path = dat_writer(upper, lower, "selig")
    u, l, frame = af.normalize(af.parse_dat(path))
    assert frame.blunt_te
    assert np.linalg.norm(u[-1] - l[-1]) > 1e-3
    assert np.abs(u - upper).max() < 1e-6 and np.abs(l - lower).max() < 1e-6


def test_truncate_te_no_rescale(naca2412):
    upper, lower = naca2412
    u, l = af.truncate_te(upper, lower, 1.0)
    assert np.isclose(u[-1, 0], 0.99) and np.isclose(l[-1, 0], 0.99)
    assert u[:, 0].max() <= 0.99 + 1e-12 and l[:, 0].max() <= 0.99 + 1e-12
    # TE gap equals the analytic thickness at x=0.99 (NACA 2412 closed TE: ~0.25% chord)
    gap = np.linalg.norm(u[-1] - l[-1])
    assert 0.002 < gap < 0.004
    assert np.allclose(u[0], upper[0])  # LE untouched


def test_sharp_te_with_zero_truncation_raises(naca2412):
    upper, lower = naca2412
    with pytest.raises(ValueError, match="sharp"):
        af.truncate_te(upper, lower, 0.0)


def test_resample_preserves_ends_and_count(naca2412):
    upper, _ = naca2412
    r = af.resample(upper, 80)
    assert r.shape == (80, 2)
    assert np.allclose(r[0], upper[0]) and np.allclose(r[-1], upper[-1])
    assert np.all(np.diff(r[:, 0]) > 0)  # x monotonic on a NACA upper surface


def test_load_pipeline_and_outline_order():
    a = af.load(af.fetch("s1223"), te_truncate_pct=1.0, n_per_surface=80)
    o = a.outline()
    assert o.shape == (159, 2)
    assert np.isclose(o[0, 0], 0.99) and np.isclose(o[-1, 0], 0.99)   # starts/ends at the TE cut
    assert o[0, 1] > o[-1, 1]                                            # starts on the upper surface
    assert np.linalg.norm(o[79]) < 0.003                                 # LE in the middle
    assert 0.11 < a.max_thickness()[1] < 0.13                            # S1223 is ~12.1 % thick
    assert 0.06 < a.area() < 0.07
    assert a.camber(0.4) > 0.07                                          # heavily cambered


def test_gurney_adds_tab_below_lower_te(naca2412):
    upper, lower = af.truncate_te(*naca2412, 1.0)
    lower = af.resample(lower, 80)
    g = af.add_gurney(lower, 1.5, 0.01, 80)
    assert g.shape == (82, 2)                       # n + 2 corners, independent of tab width
    assert g[-1, 0] == pytest.approx(0.99)          # aft-bottom corner under the TE cut
    assert g[-2, 0] == pytest.approx(0.98)          # forward-bottom corner
    assert g[-3, 0] == pytest.approx(0.98)          # where the tab leaves the lower surface
    assert g[-1, 1] == pytest.approx(g[-3, 1] - 0.015)
    a = af.load(af.fetch("s1223"), te_truncate_pct=1.0, n_per_surface=80, gurney_pct=1.5, gurney_thickness=0.01)
    assert a.n_corners == 2 and a.outline().shape == (161, 2)
    assert 0.11 < a.max_thickness()[1] < 0.13       # tab ignored by thickness/camber
