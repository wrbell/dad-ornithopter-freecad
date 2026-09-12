#!/usr/bin/env python
"""End-to-end contract check of the agentcad integration (stdlib only; CI runs this too).

    .venv/bin/python smoke_agentcad.py --agentcad .venv-agentcad/bin/agentcad     # local
    python smoke_agentcad.py --agentcad agentcad                                    # CI

Runs the agentcad CLI as a subprocess and parses ONLY stdout as JSON (stderr carries progress).
No rendering, so it needs no display: dry run, core-only run, check-spec, measure, and two failure cases.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MODEL = "models/wingtip_agentcad.py"
SPEC = "models/wingtip_spec.json"
EXPECTED_DIMS = {"x": 163.34, "y": 270.0, "z": 26.15}


def run(agentcad: str, *args: str, expect_exit: int = 0) -> dict:
    env = dict(os.environ, AGENTCAD_RUN_TIMEOUT_S=os.environ.get("AGENTCAD_RUN_TIMEOUT_S", "600"))
    p = subprocess.run([agentcad, *args], capture_output=True, text=True, env=env)
    if p.returncode != expect_exit:
        sys.stderr.write(p.stderr[-2000:])
        raise SystemExit(f"agentcad {' '.join(args)}: exit {p.returncode}, expected {expect_exit}\n{p.stdout[-2000:]}")
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise SystemExit(f"agentcad {' '.join(args)}: stdout is not JSON ({e}):\n{p.stdout[:2000]}") from e


def check(cond: bool, what: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agentcad", default=".venv-agentcad/bin/agentcad")
    ap.add_argument("--label", default="smoke")
    a = ap.parse_args()
    os.chdir(Path(__file__).resolve().parent)
    common = ["--no-daemon"]

    print("[1] context")
    ctx = run(a.agentcad, "context")
    check(ctx.get("status") == "success", f"project {ctx.get('project')!r}, tool {ctx.get('tool_version')}")

    print("[2] dry run (metrics only)")
    d = run(a.agentcad, "run", MODEL, "--label", a.label, "--dry-run", *common)
    m = d.get("metrics", {})
    check(d.get("status") == "success" and d.get("runtime") == "cadquery", "status success, cadquery runtime")
    check(m.get("is_valid") is True, "kernel + shell + mesh validation passed")
    dims = m.get("dimensions", {})
    check(all(abs(dims.get(k, 0) - v) < 0.5 for k, v in EXPECTED_DIMS.items()), f"dimensions {dims}")
    layers = d.get("validation", {}).get("layers", {})
    check(layers.get("structure", {}).get("solid_count") == 1, "exactly one solid (every boss web bridges the skins)")
    warns = d.get("warnings", [])
    check(any("est. mass" in w for w in warns), f"mass estimate surfaced in warnings ({len(warns)} warnings)")

    print("[3] core-only run (STEP, no preview/diff/viewer)")
    r = run(a.agentcad, "run", MODEL, "--label", a.label, "--no-preview", "--no-diff", "--no-view", *common)
    step = r.get("outputs", {}).get("step")
    check(r.get("status") == "success" and r.get("artifact_created") is True, f"version {r.get('version')} created")
    check(bool(step) and Path(step).is_file() and Path(step).stat().st_size > 100_000, f"STEP written: {step}")

    print("[4] check-spec + measure on the delivered STEP")
    cs = run(a.agentcad, "check-spec", step, SPEC, *common)
    check(cs.get("passed") is True, "three 4.2 mm bores found (spec passed)")
    me = run(a.agentcad, "measure", step, "--cylinders-only", "--diameter", "4.2", *common)
    check(me.get("status") == "success", "measure ran")

    print("[5] failure cases")
    neg = run(
        a.agentcad,
        "run",
        MODEL,
        "--label",
        "neg",
        "--dry-run",
        "--params",
        "hole_min_wall_mm=1.5",
        *common,
        expect_exit=1,
    )
    check(
        "mount hole validation failed" in neg.get("message", "") and "'aft'" in neg.get("message", ""),
        "hole validation error surfaces with the hole name",
    )
    unk = run(a.agentcad, "run", MODEL, "--label", "neg2", "--dry-run", "--params", "nope=1", *common, expect_exit=1)
    check("Unknown parameter" in unk.get("message", ""), "unknown --params key rejected")
    print("agentcad integration OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
