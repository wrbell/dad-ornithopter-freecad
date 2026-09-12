import pytest

from ornitho import airfoil as af
from ornitho.config import Hole, WingConfig
from ornitho.validate import HoleValidationError, check_holes, simpson_volume


@pytest.fixture
def setup():
    def _make(**over):
        cfg = WingConfig.from_dict(over)
        foil = af.load(af.fetch("s1223"), te_truncate_pct=cfg.te_truncate_pct, n_per_surface=cfg.n_per_surface)
        pf = cfg.planform()
        root3 = pf.station(0).place_unit(foil.outline())
        tip3 = pf.station(1).place_unit(foil.outline())
        return cfg, foil, root3, tip3

    return _make


def test_default_holes_pass(setup):
    cfg, foil, r, t = setup()
    res = check_holes(cfg, foil, r, t)
    assert [h["name"] for h in res] == ["fwd", "mid", "aft"]
    assert all(h["min_clearance"] > 0 for h in res)
    # auto-centred on the camber line: z is well above the chord line for S1223
    assert all(h["z"] > 5 for h in res)


def test_hole_at_95pct_raises(setup):
    cfg, foil, r, t = setup(mount_holes=[Hole("way_aft", 95.0, 4.2)])
    with pytest.raises(HoleValidationError, match="way_aft"):
        check_holes(cfg, foil, r, t)


def test_hole_on_chord_line_at_65pct_raises(setup):
    # S1223 is cambered: at 65 % the lower surface is ~6 % c ABOVE the chord line
    cfg, foil, r, t = setup(mount_holes=[Hole("aft_chordline", 65.0, 4.2, z_pct=0.0)])
    with pytest.raises(HoleValidationError, match="aft_chordline"):
        check_holes(cfg, foil, r, t)


def test_overlapping_bosses_raise(setup):
    cfg, foil, r, t = setup(mount_holes=[Hole("a", 30.0, 4.2), Hole("b", 33.0, 4.2)])
    with pytest.raises(HoleValidationError, match="too close"):
        check_holes(cfg, foil, r, t)


def test_unknown_config_key_rejected():
    with pytest.raises(KeyError, match="unknown config key"):
        WingConfig.from_dict({"root_chord": 165})


def test_hole_tuple_forms():
    cfg = WingConfig.from_dict({"mount_holes": [(18, 5, 4.2), ("x", 40, 3.0), {"name": "y", "x_pct": 60, "d_mm": 3}]})
    assert [h.name for h in cfg.mount_holes] == ["h18", "x", "y"]
    assert cfg.mount_holes[0].z_pct == 5 and cfg.mount_holes[1].z_pct is None


def test_simpson_volume_matches_prism(setup):
    cfg, foil, r, t = setup(tip_chord_mm=165, le_sweep_deg=0, washout_deg=0)
    assert simpson_volume(r, t, 270) == pytest.approx(foil.area() * 165**2 * 270, rel=1e-9)


def test_aft_hole_needs_thin_min_wall(setup):
    # the 65 % placeholder only fits a 4.2 mm hole with ~1 mm of material; 2.5 mm must fail loudly
    cfg, foil, r, t = setup(hole_min_wall_mm=2.5)
    with pytest.raises(HoleValidationError, match="aft"):
        check_holes(cfg, foil, r, t)
