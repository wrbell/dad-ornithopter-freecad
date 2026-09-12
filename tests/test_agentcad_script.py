"""The agentcad model script must honour the CQGI contract and build the same wing as wingtip.py."""

import ast
import runpy
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "models" / "wingtip_agentcad.py"


def _tree():
    return ast.parse(SRC.read_text())


def test_params_block_is_cqgi_safe():
    """Top-level assignments before the first import must be plain scalar literals."""
    seen_import = False
    n_params = 0
    for node in _tree().body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            seen_import = True
        if isinstance(node, ast.Assign) and not seen_import:
            assert len(node.targets) == 1 and isinstance(node.targets[0], ast.Name), ast.dump(node)
            assert isinstance(node.value, ast.Constant), f"{node.targets[0].id}: not a literal"
            assert node.value.value is not None, f"{node.targets[0].id}: None breaks CQGI stdout"
            assert isinstance(node.value.value, int | float | str | bool)
            n_params += 1
    assert n_params >= 15
    names = [n.targets[0].id for n in _tree().body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)]
    for required in ("root_chord_mm", "wall_thickness_mm", "hole_min_wall_mm", "hole_aft_x_pct"):
        assert required in names


def test_calls_show_object_and_never_prints():
    calls = [n.func.id for n in ast.walk(_tree()) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "show_object" in calls
    assert "print" not in calls


@pytest.mark.slow
def test_script_builds_valid_wing_on_main_kernel():
    captured = {}

    def show_object(obj, **kw):
        captured["obj"], captured["kw"] = obj, kw

    runpy.run_path(str(SRC), init_globals={"show_object": show_object})
    solid = captured["obj"].val()
    assert solid.isValid()
    bb = solid.BoundingBox()
    assert bb.ymax == pytest.approx(270.0, abs=0.2) and bb.xmax == pytest.approx(163.35, abs=0.2)
    assert captured["kw"].get("name") == "wingtip"
