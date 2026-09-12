# Ornithopter CAD — instructions for Claude Code

Parametric TPU wingtip for an 8-wing flapping-wing (ornithopter) drone. Root section is the stock UIUC S1223
at 165 mm chord (must match the existing rib), tip 80 mm, span 270 mm, 15° LE sweep, 8° washout, hollow shell
with three spanwise mounting holes. Mass target ≤ 110 g per tip; the whole aircraft is ~4.2 kg with a thin
hover margin, so every gram counts.

- `ornitho/` is the library (airfoil loader, section math, CadQuery geometry, hole validation, mass report, renders).
- `wingtip.py` is the human loop: edit `CONFIG`, run, look at `out/*.png`, read `out/report.txt`.
- `models/wingtip_agentcad.py` is the agent loop: the same geometry exposed to agentcad (versioned runs,
  previews, measure, diff, viewer) through its CadQuery runtime.

## Two toolchains, never mixed

| venv | what runs there | kernel |
|---|---|---|
| `.venv` | `wingtip.py`, `pytest`, pyvista renders, `out/report.txt` | cadquery 2.8 / OpenCascade 7.9 |
| `.venv-agentcad` | `agentcad` CLI and the MCP server | cadquery 2.7 / OpenCascade 7.8 (agentcad's pin) |

`make setup` builds both. Do not pip-install across them; the two OpenCascade builds cannot share a venv.

```bash
make run                                   # full build + STEP/STL + PNGs + report   (.venv)
make test / make slow / make lint          # unit tests, OCCT tests, ruff             (.venv)
make agentcad-dry LABEL=v1                 # validity + metrics, no version consumed  (.venv-agentcad)
make agentcad-run LABEL=thin ARGS="--params wall_thickness_mm=1.6"   # versioned run + renders
make agentcad-smoke                        # end-to-end contract check of the integration
```

## Rules

1. **Coordinate frame.** x chordwise, positive aft, root LE at 0. y spanwise, positive outboard, rib face at 0.
   z up. Sections stay in planes y = const. Twist is about the quarter chord, positive = nose down. If a view
   looks wrong, fix the viewer or the camera; never re-orient the geometry to match a picture.
2. **Hole validation must pass.** `ornitho.validate.check_holes` runs before any OCCT work. A
   `HoleValidationError` (agentcad reports `status: failed` with "mount hole validation failed") is a design
   problem: move or shrink the hole. Never lower `hole_min_wall_mm` below 1.0 or catch the exception to make
   it pass. When you change holes, report each hole's minimum clearance from the report or the warnings.
3. **Look at the renders before saying done.** After any geometry change, view `out/wingtip_iso.png`,
   `out/wingtip_root.png` and `out/section.png` (from `make run`), or `build/vN_label/preview.png` and
   `build/vN_label/renders/*.png` (from agentcad), and say what you saw: LE forward, span to +y, tip nose-down,
   cavity with solid trailing edge, three full-height boss webs with bores. Metrics are not a substitute for looking.
4. **Mass comes from `out/report.txt`.** It uses a fine triangulation of the solid plus the 2D wall table.
   agentcad's `metrics.volume` is OpenCascade's analytic integration, measured about 25 % low on this spline
   loft. Use it for validity, bounding box and diffs only; never quote it as mass.
5. **Keep the design anchors.** `root_chord_mm = 165` and the stock S1223 stay unless explicitly told
   otherwise. Keep CadQuery and the kernel pins; a build123d port or a pin bump needs an explicit request and
   a green `make slow`.
6. **Commit the evidence.** Geometry changes are committed together with the regenerated `out/*.png`,
   `out/report.txt` and `out/wingtip_run.json` so the git history stays visual. STEP/STL are gitignored.

## Using agentcad here

- Run models through the CLI, not the MCP `run` tool: `make agentcad-run LABEL=<slug> ARGS="--params k=v"`.
  The CLI prints one JSON object on stdout and progress on stderr. (With current click versions the MCP
  `run` and `inspect` tools return their JSON wrapped inside an error envelope; the other MCP tools such as
  `measure`, `render`, `diff`, `check_spec`, `docs`, `context` are clean and fine to use.)
- `--params` only touches the scalar PARAMS block at the top of `models/wingtip_agentcad.py`. Anything else is
  edited in the file. Labels are short slugs (`thin16`, `aft60`).
- `agentcad check-spec build/vN_label/output.step models/wingtip_spec.json` proves the three 4.2 mm bores exist
  in the delivered STEP.
- The response's `warnings` array carries the 2D mass estimate and a note for any hole with less than 0.5 mm
  of spare clearance. The default aft hole (65 % chord) is that tight; it is a placeholder until the rib is measured.
- Artifacts live under `build/` (gitignored). `make agentcad-import LABEL=x` adopts `out/wingtip.step` from the
  main kernel as an agentcad version when you want to measure or diff the authoritative STEP.

## Definition of done

`make lint test` green; `make slow` if `ornitho/` changed; `make run` and the renders viewed; `make agentcad-smoke`
if the model script, packaging or requirements changed; the mass versus the 110 g target stated in the summary.

## Gotchas

- In `models/wingtip_agentcad.py`: no `print()` (stdout is agentcad's JSON), no `= None`, tuples or negative
  literals in the PARAMS block (CQGI cannot parametrise them), and keep the block that purges `ornitho` from
  `sys.modules` (agentcad's daemon and MCP server are long-lived and would otherwise cache stale code).
- `AGENTCAD_RUN_TIMEOUT_S` is exported as 600 by the Makefile; the build takes about 10 s but exact 3D diffs
  can take longer.
- After moving or renaming the folder: `rm -rf .venv .venv-agentcad build && make setup` (venv shebangs, the
  editable install and `build/agentcad.json` all record the absolute path).
- `.claude/skills/agentcad/SKILL.md` and the managed block in `AGENTS.md` are generated by agentcad. Refresh
  them with `make agentcad-guide` after upgrading agentcad; do not edit them by hand.
- OpenCascade's `Shape.Volume()` is unreliable on these many-span spline solids; use `ornitho.geometry.volume`.
- The S1223 trailing edge is only 0.42 mm thick at the default 1 % truncation; a printable 1 mm edge needs
  about 2.5–3 %. Flag this when printing comes up.
