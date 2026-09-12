import numpy as np
import pytest
from shapely.geometry import Polygon

from ornitho import airfoil as af
from ornitho import sections as sec


@pytest.fixture
def pf():
    return sec.Planform(root_chord=165, tip_chord=80, span=270, le_sweep_deg=15, washout_deg=8, dihedral_deg=0)


@pytest.fixture
def s1223():
    return af.load(af.fetch("s1223"), te_truncate_pct=1.0, n_per_surface=80)


def test_station_linear(pf):
    r, m, t = pf.station(0), pf.station(0.5), pf.station(1)
    assert (r.chord, m.chord, t.chord) == (165, 122.5, 80)
    assert r.x_le == 0 and t.x_le == pytest.approx(270 * np.tan(np.radians(15)))
    assert (r.twist_deg, t.twist_deg) == (0, 8) and t.y == 270 and t.z_dih == 0


def test_root_placement_is_identity(pf, s1223):
    p = pf.station(0).place_unit(s1223.outline())
    o = s1223.outline() * 165
    assert np.allclose(p[:, 0], o[:, 0]) and np.allclose(p[:, 2], o[:, 1]) and np.all(p[:, 1] == 0)


def test_positive_washout_is_nose_down(pf, s1223):
    tip = pf.station(1.0).place_unit(s1223.outline())
    i_le = int(np.argmin(np.linalg.norm(s1223.outline(), axis=1)))
    z_le, z_te = tip[i_le, 2], 0.5 * (tip[0, 2] + tip[-1, 2])
    assert z_le < z_te
    # quarter chord point is unmoved by the twist
    st = pf.station(1.0)
    qc = st.place_mm(np.array([[0.25 * st.chord, 0.0]]))[0]
    assert qc[0] == pytest.approx(st.x_le + 0.25 * st.chord) and qc[2] == pytest.approx(0.0)
    # LE-to-TE distance preserved under rotation (nose point is not exactly the origin on S1223)
    o = s1223.outline()
    expected = np.linalg.norm(o[i_le] - 0.5 * (o[0] + o[-1])) * 80
    assert np.linalg.norm(tip[i_le] - 0.5 * (tip[0] + tip[-1])) == pytest.approx(expected, abs=1e-9)


def test_section_at_and_area(pf, s1223):
    root = pf.station(0).place_unit(s1223.outline())
    tip = pf.station(1).place_unit(s1223.outline())
    mid = sec.section_at(root, tip, 0.5)
    assert np.all(mid[:, 1] == pytest.approx(135))
    a_r, a_m, a_t = (sec.area_xz(x) for x in (root, mid, tip))
    assert a_r == pytest.approx(s1223.area() * 165**2, rel=1e-9)
    assert a_t < a_m < a_r


def test_inset_uniform_wall(s1223):
    out = s1223.outline() * 165
    u, lo = sec.inset(out, 2.5)
    assert u.shape == (60, 2) and lo.shape == (60, 2)
    assert np.allclose(u[0], lo[0])  # shared nose
    assert np.allclose(u[-1], lo[-1])  # collapsed tail cusp (TE thinner than 5 mm)
    inner = Polygon(sec.inner_outline(u, lo))
    outer = Polygon(out)
    assert inner.is_valid and outer.contains(inner)
    # every inner vertex is ~t from the outer boundary (mitre corners excepted)
    d = np.array([outer.exterior.distance(__import__("shapely").geometry.Point(p)) for p in inner.exterior.coords])
    assert np.percentile(d, 5) > 2.4 and np.median(d) == pytest.approx(2.5, abs=0.05)
    assert sec.inset(out, 2.5)[0][-1, 0] < 0.99 * 165  # cusp forward of the TE cut


def test_inset_thinner_wall_larger_cavity(s1223):
    out = s1223.outline() * 80
    a = [Polygon(sec.inner_outline(*sec.inset(out, t))).area for t in (1.2, 2.0, 2.5)]
    assert a[0] > a[1] > a[2] > 0


def test_inset_too_thick_raises(s1223):
    with pytest.raises(ValueError, match="no cavity"):
        sec.inset(s1223.outline() * 80, 6.0)


def test_circle_inside():
    sq = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    ok, c = sec.circle_inside(sq, 5, 5, 2)
    assert ok and c == pytest.approx(3)
    ok, c = sec.circle_inside(sq, 9, 5, 2)
    assert not ok and c == pytest.approx(-1)
