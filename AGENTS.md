<!-- agentcad:start -->
<!-- agentcad-guide: b3ec3840a2e2 -->
# agentcad — CAD tool for AI agents

You have access to `agentcad` in a CadQuery compatibility project. The CLI
turns CadQuery Python scripts into 3D geometry. Operational commands return structured JSON with `"command"` and
`"status"` keys. `--help` and `agentcad docs` return readable text.

## CadQuery compatibility setup

CadQuery is an optional extra, not part of the default install.

```bash
pip install "agentcad[cadquery]"
agentcad init --name <project_name> --runtime cadquery
```

`init` creates the project and installs this guide, so nothing else is
required before the core workflow. `agentcad --help` and `agentcad docs` hold
the full command reference when you need more than this guide.

If `agentcad.json` already exists in the selected build directory (the project
root by default), this project is already initialized — skip `init` and go
straight to the core workflow. Use `agentcad context` to check configured state.

## Core workflow

To separate generated artifacts from source, set `build_dir = "./build"` in
`agentcad.toml` before `agentcad init`. Use `--build-dir PATH` for one command;
it selects independent history and does not edit configuration. Relative build
paths resolve from the project root, including from nested directories.
`agentcad context` reports the resolved build root. Use returned artifact paths;
`--label` names a version and deprecated `--output` is only a label alias.
See `agentcad docs artifacts` for initialization, overrides, and recovery.

1. **Write a script.** No imports needed — `cq`, `show_object`, and
   CadQuery compatibility helpers are pre-injected. At least one
   `show_object(result)` call is required.

2. **Dry-run first** to check metrics without consuming a version:
   ```bash
   agentcad run script.py --label test --dry-run
   ```
   Check `volume`, `dimensions`, `is_valid` in the response. `is_valid` is the
   deliverable verdict: the kernel check, every shell closed, and a manifold
   mesh. Do not hand a part off until it is `true`; `false` names the failing
   layer in `validation.first_failure`, `null` means a check timed out.

3. **Run for real.** Visual feedback is on by default:
   ```bash
   agentcad run script.py --label label
   ```
   A normal successful iteration can produce (paths in the JSON response):
   - `preview.png` — balanced top, bottom, upper-iso, and lower-iso composite.
     **Read this** to confirm the part looks right before iterating. The lower
     views expose geometry that a top view can hide.
   - `diff.side_by_side` — side-by-side PNG vs the most recent successful prior
     version, when one exists and automatic diff is enabled. **Read this** when
     iterating to see what your change did.
   - `diff.overlay` — centered 2D visual-overlap map (coincident gray,
     reference-only blue, candidate-only orange). It helps locate silhouette
     changes but does not prove physical correctness or shared 3D volume.
   - `viewer.html` — interactive 3D review viewer for the user unless viewer
     artifacts are disabled (humans only;
     you can't render HTML). It remains an immutable version snapshot.
     `project_viewer.url` is the live project URL: share it with the human and
     leave its tab open while iterating. Successful builds update that page
     automatically, preserving the camera and compatible review settings.
     From v2, A=previous and B=current are already loaded with synchronized
     A/B, side-by-side, overlay, diff-image, and Parts-tab change review.

   Pass `--no-preview` only for tight parametric sweeps where latency matters.
   Pass `--no-view` only when browser launch would disrupt an unattended or
   high-volume run.

   For a core-only iteration, pass
   `--no-preview --no-diff --no-view`. This writes `output.step`, the saved
   script, `meta.json` (including metrics), and explicitly requested exports
   without generating previews, automatic comparisons, viewer assets, or
   opening a browser. You can still run an explicit
   `agentcad diff OLD NEW` later.

   When a comparison is slow or incomplete, read `comparison_phases` in the
   JSON response. `source_loading`, `comparison_rendering`,
   `projection_comparison`, `exact_3d_comparison`,
   `approximate_3d_comparison`, `difference_artifact_export`, and
   `viewer_generation` each report a status
   and, when attempted, `duration_ms`. The largest duration identifies the
   expensive stage; a failed exact phase does not erase a successful projection.
   Exact 3D work has a 30-second default worker budget. Set
   `AGENTCAD_DIFF_TIMEOUT_S=N` to override it (`0` disables the dedicated limit
   for diagnostics). A timeout leaves the core version and projection usable,
   then runs a bounded voxel fallback. Approximate results report
   `method=approximate_voxel_volume`, `resolution_mm`, and a non-strict
   `error_estimate`; its `absolute_volume` values are heuristic errors, not
   measurements. `exact_attempt` retains the exact failure. Use
   `AGENTCAD_APPROX_DIFF_TIMEOUT_S` and `AGENTCAD_APPROX_RESOLUTION_MM` to tune
   the fallback. If exact volumes are still needed, run
   `agentcad diff OLD NEW` with a larger budget; do not rerun the original CAD
   command and create a duplicate version.

   Daemon-routed commands may run beyond 30 seconds. Progress heartbeats appear
   on stderr while stdout stays reserved for the final JSON response, and the
   submitted command is never automatically retried. If a silent or lost daemon
   returns `outcome: "unknown"` and `retry_safe: false`, inspect `agentcad
   context`, existing outputs, and `agentcad daemon status` before retrying; the
   original command may already have completed.

4. **Review with the user.** The live project viewer opens automatically and
   reuses an active tab. Share `project_viewer.url` for ongoing iteration;
   share `viewer` for a fixed version. Use `agentcad viewer open` to reopen the
   project, and `agentcad viewer status` or `stop` for service diagnostics. On v2+
   start with its previous/current comparison, then use A/B, Overlay, and Parts
   without selecting files manually. Use `agentcad view old.step new.step` only
   for an explicit non-adjacent comparison.

5. **Read the validation report if invalid.** A `status: invalid_geometry` run
   already carries `validation`: the failing layer, free edges by ID with
   endpoints, or the located mesh defect, plus a `suggestion`. For an existing
   file:
   ```bash
   agentcad inspect v1_label/output.step
   ```
   Intentional surfaces or sheet bodies: pass `--validation-profile kernel`.

6. **Measure feature sizes.** For dimensions beyond top-level metrics:
   ```bash
   agentcad measure v1_label/output.step
   ```
   Use this for hole diameters, cylindrical boss diameters, edge lengths,
   face areas, and full per-feature measurements with `--features`.

7. **Check explicit feature requirements.** If the prompt names measurable
   holes, bores, or cylindrical bosses, write them into `spec.json` before
   final handoff:
   ```json
   {"features":[{"name":"bolt_holes","type":"cylinder","diameter_mm":6,"count":4}]}
   ```
   Then run:
   ```bash
   agentcad check-spec v1_label/output.step spec.json
   ```
   Revise the CAD if `passed` is false. `status: success` only means the
   comparison ran; `passed` is the actual spec-check result. If you include
   `axis`, copy it from `agentcad measure`'s `cylindrical_features[].axis`.

8. **Iterate.** Fix the script, run with a new `--label` value. Use
   `agentcad diff 1 2` to compare versions.

## Script writing rules

- This is a CadQuery compatibility project. Keep scripts on the CadQuery API.
- `show_object(result)` is required — at least one call.
- `cq`, `show_object`, and compatibility helpers are pre-injected, so a basic
  script needs no import:
  ```python
  part = cq.Workplane('XY').box(10, 20, 5)
  show_object(part)
  ```
- Helpers that operate on `TopoDS_Shape` use `.val().wrapped` as the bridge:
  ```python
  part = cq.Workplane('XY').box(10, 20, 5).val().wrapped
  moved = translate(part, 50, 0, 0)
  ```
- Imported-geometry Booleans should use `safe_cut`, `safe_intersection`, or
  `safe_fuse`; these independently copy inputs and reject invalid or
  physically impossible output.
- To show raw helper output:
  ```python
  show_object(cq.Workplane('XY').newObject([cq.Shape.cast(topo_shape)]))
  ```
- For OCP internals (`gp_Pnt`, `BRepPrimAPI`, etc.), import manually.

## Key commands

| Command | Purpose |
|---------|---------|
| `agentcad init --name NAME --runtime cadquery` | Initialize compatibility project |
| `agentcad run SCRIPT --label LABEL` | Execute script, produce STEP + metrics |
| `agentcad run ... --dry-run` | Metrics only, no version consumed |
| `agentcad run ... --no-preview` | Suppress preview (on by default) |
| `agentcad run ... --no-diff` | Suppress automatic prior-version comparison |
| `agentcad run ... --no-view` | Suppress automatic browser review |
| `agentcad run ... --render iso,front` | PNG views |
| `agentcad run ... --export stl,glb` | Mesh export |
| `agentcad run ... --params k=v,k=v` | Override script parameters |
| `agentcad render STEP --view SPEC` | Post-hoc renders with camera control |
| `agentcad export STEP --format stl,glb` | Post-hoc mesh export |
| `agentcad measure STEP` | Dimensional report (overall metrics + feature sizes) |
| `agentcad check-spec STEP spec.json` | Pass/fail checklist against intended cylindrical features |
| `agentcad inspect STEP` | Bounded topology report with observable validation phases |
| `agentcad parts list REF` | List parts captured for a version |
| `agentcad parts show REF ID` | Show one versioned part by stable id |
| `agentcad diff REF1 REF2` | Compare versions |
| `agentcad context` | Project state and interrupted-version recovery candidates |
| `agentcad recover VERSION_DIR` | Validate and reconcile interrupted history without deleting files |
| `agentcad docs [SECTION]` | Runtime-aware built-in documentation |
| `agentcad instructions install` | Refresh this guide in AGENTS.md/CLAUDE.md |
| `agentcad view FILE [FILE_B]` | Open one model or an explicit synchronized A/B comparison |

`--label` names a version; read the generated file from `outputs.step`.
`--output` remains a deprecated compatibility alias and is not a path option.

## Debugging playbook

1. **Check metrics first** — `volume` and `dimensions` catch most issues.
2. **Read `preview.png`** — the 4-view composite. Fastest way to spot obvious problems.
3. **Read `diff.side_by_side`** if iterating — confirms your change did what you intended.
4. **Negative volume?** Wire winding is backwards (CW instead of CCW).
5. **Need a hole diameter or edge length?** Run `agentcad measure output.step`.
6. **Need to verify explicit hole/bore counts?** Write `spec.json`, then run
   `agentcad check-spec output.step spec.json`.
7. **is_valid: false?** Read `validation.first_failure` and its layer entry:
   `shell_closure` lists the free edges with endpoints, `mesh_manifold` locates
   the defect and names the faces, `brep_check` lists kernel error classes.
8. **Open shell?** `validation.layers.shell_closure.free_edges` traces the gap;
   close the profile or add the missing face. `metrics.reliable: false` means the
   volume is not physical.
9. **Complex profiles (gears, splines)?** Use subtractive construction — cut from
   a blank cylinder/box instead of building up. See `agentcad docs patterns`.
10. **A run failed?** Trust `artifact_created: false` and `outputs.step: null`;
    fix the script and execute the returned `next_actions` command. Do not write
    or truncate STEP text — `agentcad run` or `agentcad import` must create it
    through the CAD kernel.
11. **Large inspect timed out?** It is not automatically malformed. Execute the
    returned `--validate-only` action for a structural check, or the larger-budget
    deep retry. Configure the default with `AGENTCAD_INSPECT_TIMEOUT_S`.

## Patterns

- **Build at origin, then position:** Create geometry at origin, use
  `translate()` and `rotate()` to place it. These helpers copy imported
  topology before transforming it.
- **Compound vs union:** `makeCompound()` keeps assembly parts separate. Use
  `safe_fuse(source, *tools)` for imported raw shapes; `.union()` remains fine
  for ordinary newly constructed CadQuery geometry.
- **Parametric scripts:** Top-level variable assignments become overridable via
  `--params`. Use this for iteration.
- **Named parts:** `show_object(shape, id="wheel_left", name="Left wheel",
  options={"color": "red"})` creates stable part handles, per-part metrics, and
  colored GLB output.
<!-- agentcad:end -->
