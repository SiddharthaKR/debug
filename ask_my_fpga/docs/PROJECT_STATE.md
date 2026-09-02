# Ask My FPGA — Project State (checkpoint before MCP)

This is the fallback reference for the **stable, pre-MCP** design. MCP work happens
on the `MCP` git branch; `main` stays as this stable state. If the MCP direction
doesn't pan out, everything described here still stands on its own.

## What it is
A local-LLM agent that inspects **and** configures a Red Pitaya FPGA from plain
English or Japanese, by driving the **existing SharpRPL C# API** and register
catalog. It does not replace the GUI/API — it is a client of it.

## Current architecture (stable)
Five layers over the untouched SharpRPL stack:

1. **Person** — types in English or Japanese; the agent replies in the same
   language (`## Language` rule in `AGENTS.md`), keeping register/module names,
   `kind` tags, flags and numbers verbatim.
2. **Agent** — `opencode` harness loads `AGENTS.md` + `WRITE_AGENTS.md`; its bash
   permission allowlist lets the model run **only** `tools/*` and `write_tools/*`.
   Model = `gemma4` served locally by vLLM (OpenAI-compatible, 127.0.0.1:8000).
3. **Tools** — Python CLIs that print JSON. Read tools in `tools/`, write tools in
   `write_tools/`, both sitting on `fpga_common.py` + `topology.py` (Qm.n
   encode/decode, bit-fields, read-modify-write, HTTP, `x-device-token` auth,
   proxy bypass, TLS handling).
4. **Source of truth (local, off git)** — `settings.json` (register catalog:
   alias->address->type) via `catalog_path`; `topology.yaml` (fixed wiring +
   selectors) via `topology_path`. The agent never invents wiring or registers.
5. **Config** — `config.json`: the 3 must-set knobs are `device_id`,
   `device_token`, `mode` (`live`/`replay`), plus endpoints and decode constants.

**SharpRPL stack (unchanged):** tools call the C# ASP.NET Minimal API over HTTPS
(and `/ws/wave` for capture); C# drives the Native-C TCP sender per device to the
Red Pitaya FPGA (ADC -> DSP chain -> DAC/SCOPE).

## What's built and working
- **Read tools:** get_status, get_modules, get_register_info, get_parameter,
  get_fpga_state, get_output_status, get_sessions, get_signal_path,
  get_affecting_parameters, get_reachable, capture_analyze_signal, topology_check.
- **Write tools:** set_signal_path, set_parameter, configure_asg, configure_scope.
- **Provenance:** every result tagged `fact` / `config` / `measurement` / `unknown`.
- **Live-proven:** get_parameter (PI_SET_KP -> -0.125), full NL loop in opencode,
  get_signal_path to DAC0. Writes verified in replay.
- **Docs:** bilingual usage guide (`docs/USAGE.en.md` + `docs/USAGE.ja.md`,
  mirrored section-for-section), README links, AGENTS.md language rule.

## Safety model (current)
Reads are always free. Every write is **dry-run -> show -> human approval ->
`--apply`**, with per-bitfield read-modify-write and read-back verification. Two
things enforce it: no raw-HTTP path is reachable (bash allowlist), and `--apply`
is a human-typed flag.

## Privacy / git
Repo = `github.com/SiddharthaKR/debug` (git root is the parent `debug` repo;
project lives in `ask_my_fpga/`). `.gitignore` keeps `config.json` (token),
`topology/topology.yaml`, and the fixture samples local. `config.example.json` is
the sanitized template. RTL (`dsp_tp.sv`) is never shared with any AI.

## MCP layer — BUILT on the `MCP` branch (`mcp_server/`)
The tools are also exposed as an **MCP server** so any MCP-capable client/harness
can use them, not just opencode's bash. Built and validated in replay
(`mcp_server/selftest.py`: 10/10; 17 tools register; end-to-end plan→commit works).
Design:

1. **Value:** client/harness-agnostic — the reason to do it.
2. **Transport:** STDIO, **local only** (no network endpoint).
3. **Safety:** two-phase `plan_write` (read-only, returns the register diff + a
   plan token) then `commit_write` (re-reads and re-verifies against the plan,
   aborts if state moved) — one human review between. "Write is fine, review once."
4. **Secrets:** `x-device-token` and `device_id` live in the MCP server's
   config/env, never as tool parameters the model can see.
5. **Tools:** one MCP tool per existing script; `readOnlyHint` / `destructiveHint`
   annotations; keep `kind` in structured content.
6. **Integrity:** `commit_write` re-verifies against the plan (yes).
7. **No replay** in the MCP server — live only.

Implementation note: the MCP server **imports** `fpga_common.py` / `topology.py`
and calls the functions — it does not reshell the CLIs or reimplement decoding.
Python MCP SDK (pinned `mcp>=1.2,<2` — v1 FastMCP; v2 renamed the API).

Files: `mcp_server/server.py` (thin MCP wiring + annotations), `fpga_ops.py`
(operations + plan/commit, imports fpga_common/topology and the tool plan-builders),
`selftest.py`, `requirements.txt`, `opencode.mcp.example.json`,
`claude_desktop.mcp.example.json`. Setup guide: `docs/MCP.md`. Reads + `plan_*` are
read-only; `commit_write` is the only destructive tool; token/deviceId stay in
config.json via fpga_common (never tool parameters).
