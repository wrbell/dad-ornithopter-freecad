# Handoff: running this with Claude Code on a new Mac

One-time setup (10 minutes, needs Python 3.10–3.12 and about 3 GB of disk):

```bash
git clone git@github.com:wrbell/ornithopter-cad.git
cd ornithopter-cad
make setup            # builds .venv (pipeline) and .venv-agentcad (agentcad + MCP server)
make run              # sanity check: writes out/*.png and out/report.txt in ~15 s
```

Open Claude Code in the folder:

```bash
claude
```

The first launch asks you to approve the project's `agentcad` MCP server; say yes. The `agentcad` skill and
the project rules (`CLAUDE.md`) are picked up automatically. Check with `/mcp` inside the session or
`claude mcp list` in the terminal; `agentcad` should show as connected.

## Prompts that work

- "Thin the wall to 1.6 mm, rebuild, and show me the root view and the mass table."
- "Move the aft mounting hole to 58 % chord with 5 mm material around it and tell me the clearance at every hole."
- "Compare 6° and 8° washout side by side and tell me what changed in the planform and the tip section."
- "The rib holes measure at 17.5 %, 41 % and 60 % chord, 4.3 mm diameter, on the camber line. Update the
  config, validate, and regenerate the STEP."

## Where to look

| you want | open |
|---|---|
| the shape, quickly | `out/wingtip_iso.png`, `out/wingtip_root.png`, `out/section.png` |
| mass and the wall-thickness trade | `out/report.txt` |
| a file for the slicer / another CAD tool | `out/wingtip.stl`, `out/wingtip.step` |
| agentcad's versioned runs, previews and A/B viewer | `build/vN_<label>/` (`preview.png`, `renders/`, `viewer.html`) |

## If something breaks

- `make test` and `make slow` must pass; `make agentcad-smoke` checks the agentcad integration end to end.
- Moved the folder? `rm -rf .venv .venv-agentcad build && make setup`.
- A "mount hole validation failed" message means a hole would break through the skin: move it or make it
  smaller. That check is deliberate.
