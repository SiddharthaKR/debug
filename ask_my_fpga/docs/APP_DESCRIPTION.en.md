# Ask My FPGA — Application Description

> 🌐 Language: **English** · [日本語 / Japanese](APP_DESCRIPTION.ja.md)
>
> Canonical reference describing what this application is and what each tool does.
> Mirrors `APP_DESCRIPTION.ja.md` section-for-section.

## 1. What it is
Ask My FPGA is a natural-language agent that **inspects and configures a Red Pitaya
FPGA** by calling an existing **SharpRPL C# API**. A local LLM (gemma4, served by
vLLM) is driven by a coding-agent harness (opencode, or any MCP client) and calls
small Python tools. The agent never touches the FPGA directly — it is an HTTP client
of the C# API, exactly like the existing GUI. It answers questions in English or
Japanese and configures the hardware on request.

## 2. Architecture
```
user (English / 日本語)
  -> harness (opencode CLI, or an MCP client) driving gemma4 via vLLM
  -> Python tools (tools/ = read, write_tools/ = write) on fpga_common + topology
  -> SharpRPL C# API  (HTTPS + x-device-token, per deviceId)
  -> Native-C sender (TCP) -> Red Pitaya FPGA (ADC -> DSP chain -> DAC / SCOPE)
```

## 3. Core discipline: provenance tags
Every tool result carries a `kind` tag; the agent must preserve it and never upgrade
one level to another:
- **fact** — read live from the hardware.
- **config** — static metadata from the register catalog or documented fixed wiring.
- **measurement** — computed from captured signal samples.
- **unknown** — could not be resolved/verified; stated plainly, never guessed.

Rule of reasoning: keep hardware **observations** (fact/measurement) separate from
DSP **interpretation**. When inferring a cause (e.g. "why is it noisy"), do not
assert first — report observations, then give possible causes as interpretation with
explicit uncertainty.

## 4. Safety model
- **Reads are always safe** (read-only, no hardware change).
- **Writes are gated.** Each write tool defaults to a **dry run** that prints exactly
  which registers would change (current -> new). The agent shows the plan, the human
  approves, and only then is the write applied. Each write is **read-modify-write**
  (only the target bit-field changes, preserving neighbours) and **read-back
  verified**.
- In the MCP version this is a two-phase `plan_* -> commit_write`: `plan_*` returns
  the diff + a `plan_token`; `commit_write` re-reads the hardware, **aborts if state
  moved since the plan**, then applies and verifies.

## 5. Source of truth (two files)
The agent never invents wiring or registers. Two local files define the hardware:
- **settings.json** (`catalog_path`) — the register catalog: alias name -> address,
  and type (Q15.16 fixed-point / float / uint32).
- **topology.yaml** (`topology_path`) — the datapath: fixed (hardwired) edges +
  selectors (muxes, live registers). Every wire is classified exactly once.

## 6. Key concept: modules vs generators
- **Modules** are register-catalog blocks (BPF, SVF, MIX, LPF, PI, GAIN, SCOPE, …).
  `get_modules` lists these.
- **Generators (ASG0/ASG1)** are signal-generator **outputs**, driven through the C#
  output API and mapped in `config.asg_channel_map`. They are **NOT** catalog modules
  and do **NOT** appear under `get_modules`'s `modules` (they appear under
  `generators`). To generate or stop a signal, use `configure_asg` /
  `plan_configure_asg` directly — never validate an ASG with `get_modules` or
  `get_parameter`.

## 7. Read tools (tools/, always safe)
| Tool | Function | Input | kind |
|---|---|---|---|
| `get_status` | server reachability + status; also reports resolved `config_file`, `device_id`, `mode` | — | fact/unknown |
| `get_modules` | list register-catalog modules + generators (ASG0/ASG1) | — | config |
| `get_register_info` | catalog metadata for one register (type, format, default, address, shared aliases) | NAME | config/unknown |
| `get_parameter` | read one named parameter live, decoded to engineering units | NAME | fact/unknown |
| `get_fpga_state` | curated per-module live snapshot, decoded | [--modules PI,MIX] | fact |
| `get_output_status` | live generator/output status for the active device | — | fact |
| `get_sessions` | registered device sessions + the active device | — | fact |
| `get_signal_path` | trace the live signal path upstream of a node; fixed hops = config, live mux selectors = fact, plus each mux's alternatives. Answers "path to X" and "what modules affect X" | TARGET (e.g. DAC0, SCOPE0) | fact/config |
| `get_affecting_parameters` | config registers of every module on the upstream path of a node | TARGET | config |
| `get_reachable` | feasibility (topology only): what sources can route to a node; with a source, the exact selector writes | TARGET [--source SRC] | config |
| `capture_analyze_signal` | capture from /ws/wave and return a SCALAR summary only (RMS, mean/DC, peak, min, max, dominant frequency, top FFT peaks, clipping) — never raw samples | [LABEL] [--channel N] [--nsamples K] | measurement/unknown |

## 8. Write tools (write_tools/, dry-run -> approve -> apply)
| Tool | Function | Input |
|---|---|---|
| `set_parameter` | set one or more module registers in engineering units (gains, coefficients, setpoints, offsets); batch; refuses bit-packed/shared-address registers | NAME=VALUE ... [--apply] |
| `set_signal_path` | route a signal by inverting the topology into mux selector writes | SRC ... SINK [--apply] |
| `configure_asg` | configure or stop an ASG generator output (waveform, freq, amplitude, offset) | ASG0\|ASG1 --waveform --freq --amp --offset [--disable] [--stop] [--apply] |
| `configure_scope` | set what a scope taps (SCOPE_SEL) and/or the acquisition decimation; start/stop | SCOPE0\|SCOPE1 [--source SIG] [--decimation N] [--start\|--stop] [--apply] |

## 9. MCP tools (mcp_server/, same operations over MCP)
Reads: same `get_*` as above. Writes are two-phase: `plan_set_parameters`,
`plan_set_signal_path`, `plan_configure_asg`, `plan_stop_asg`, `plan_configure_scope`
(each returns a `plan_token`), then `commit_write(plan_token)` applies after human
approval, re-verifying against the plan. Secrets (`x-device-token`, `deviceId`) stay
in config, never as tool parameters.

## 10. How it answers common questions (question -> tool)
- "Is the server reachable? / which config / am I live?" -> `get_status`
- "What modules exist?" -> `get_modules`
- "What is <PARAM>?" (e.g. PI0_SET_KP) -> `get_parameter`
- "What is the signal path to DAC0?" -> `get_signal_path DAC0`
- "What modules affect DAC0?" -> `get_signal_path DAC0` (its upstream_nodes) — NOT `get_modules`
- "Which parameters affect DAC0?" -> `get_affecting_parameters DAC0`
- "Can I route ASG1 to DAC0?" -> `get_reachable DAC0 --source ASG1`
- "Why does DAC0/SCOPE0 look noisy?" -> `get_signal_path` + module state + `capture_analyze_signal`; report observations first, causes as interpretation
- "Generate a sine on ASG1" -> `configure_asg ASG1 --waveform SINE --freq 1000 --amp 0.2` (dry-run -> approve -> apply)
- "Set PI0_SET_KP to 0.5" -> `set_parameter PI0_SET_KP=0.5` (dry-run -> approve -> apply)
- "Route ASG1 through the chain to DAC0" -> `get_reachable` then `set_signal_path`
- "Show DAC0 on SCOPE0" -> `configure_scope SCOPE0 --source DAC0`

## 11. Configuration essentials (config.json)
- `device_id` — which Red Pitaya to target (null follows the GUI's activeDeviceId).
- `device_token` — sent as the `x-device-token` header; required in live mode.
- `mode` — `live` (talk to the board) or `replay` (fixtures, no hardware).
- `base_url` — the SharpRPL server; `asg_channel_map` — ASG name -> output channel.
One session targets one board; `FPGA_AGENT_CONFIG=config.rpN.json` selects the board.

## 12. Requirements
- CLI (non-MCP) path: PyYAML (topology tools); numpy + websocket-client only for
  `capture_analyze_signal` (websocket-client for live capture). No `mcp` needed.
- MCP path: additionally the `mcp` package (`mcp>=1.2,<2`).
