# Ask My FPGA — MCP server

> 🌐 Language: **English** · [日本語 / Japanese](MCP.ja.md)

An optional MCP layer over the same engineering operations, so **any MCP-capable
client** (opencode, Claude Desktop, an IDE) can use the tools — not just via
opencode's bash allowlist. It lives on the `MCP` git branch; `main` keeps the
plain CLI-tools design as a fallback. The MCP server does **not** replace the
`tools/` and `write_tools/` scripts — it imports their logic.

## What it exposes (engineering operations, not registers)
Reads (safe): `get_status`, `get_modules`, `get_parameter`, `get_register_info`,
`get_fpga_state`, `get_output_status`, `get_sessions`, `get_signal_path`,
`get_affecting_parameters`, `get_reachable`, `capture_analyze_signal`.

Writes (two-phase): `plan_set_parameters`, `plan_set_signal_path`,
`plan_configure_asg`, `plan_stop_asg`, `plan_configure_scope` — each returns a
**plan_token** — then a single `commit_write(plan_token)` applies it.

Every tool works in named parameters / engineering units (e.g.
`plan_set_parameters({"PI0_SET_KP": 0.5})`, `get_signal_path("DAC0")`). The
register map stays behind the catalog — there are no raw-address tools.

## Safety model
- Reads and every `plan_*` are marked **read-only** — they never change hardware.
- `commit_write` is the only tool marked **destructive**.
- Flow: the agent calls a `plan_*` tool, shows you the exact register diff, you
  approve, then it calls `commit_write`. **One review.**
- `commit_write` re-reads the hardware first and **aborts (writing nothing)** if
  any register moved since the plan — so an approved plan can't silently apply to
  a board that changed underneath it. Plans expire after 5 minutes.
- The `x-device-token` and `deviceId` come from `config.json` (via
  `fpga_common`) — they are **never** tool parameters the model can see.

## Install & run
```
pip install -r mcp_server/requirements.txt      # mcp>=1.2,<2, numpy, websocket-client, PyYAML
python3 mcp_server/server.py                     # speaks MCP over stdio
```
Configuration is the same `config.json` (or point `FPGA_AGENT_CONFIG` at another
file). Set `"mode": "live"` for real hardware — the MCP server is intended for
live use.

## Wire into a client
- **opencode:** merge `mcp_server/opencode.mcp.example.json` into your
  `opencode.json`.
- **Claude Desktop:** add `mcp_server/claude_desktop.mcp.example.json` (with
  absolute paths) to `claude_desktop_config.json`.

Because the plan/commit split already forces a human review before any write,
you don't need a bash allowlist for the MCP path. If your client supports
per-tool approval, gating `commit_write` adds a second backstop.

## Test without hardware
```
# set "mode": "replay" in config.json, then:
python3 mcp_server/selftest.py
```
Exercises reads + the full plan→commit loop (including the drift-abort check)
against the fixtures, and restores them afterward.

## Layout
```
mcp_server/
  server.py        # thin MCP wiring (FastMCP): registers the tools + annotations
  fpga_ops.py      # the operations + plan/commit (imports fpga_common/topology/tools)
  selftest.py      # hardware-free plan/commit test (replay)
  requirements.txt
  opencode.mcp.example.json
  claude_desktop.mcp.example.json
```
