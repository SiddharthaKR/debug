# Ask My FPGA — How to Use

> 🌐 Language: **English** · [日本語 / Japanese](USAGE.ja.md)
>
> This guide mirrors `USAGE.ja.md` section-for-section. If you edit one, edit the
> other so they stay in sync.

Ask My FPGA lets you inspect and configure a Red Pitaya FPGA by typing plain
questions and commands. A local LLM (gemma4) reads and writes the hardware through
small Python tools and your existing SharpRPL C# API.

**You can type in English or Japanese** — the agent replies in whatever language
you use. There is no language setting to switch.

## 1. Prerequisites
- The **SharpRPL C# server** is running and reachable (e.g. `https://localhost:5000`).
- **vLLM** is serving the `gemma4` model on `http://127.0.0.1:8000/v1`.
- **opencode** is installed.
- `config.json` is filled in (base_url, catalog_path, device token). Start from
  `config.example.json` if you don't have one.
- Python deps for the signal tool: `pip install -r requirements.txt`.

## What you must set (config.json)
Everything else has a sane default. Only three things must be set for your board:

| Thing | `config.json` key | What it is |
|---|---|---|
| **Device ID** | `device_id` | Which board to talk to. `null` = follow `activeDeviceId` from `/api/status`; a number pins one of up to 4 devices. |
| **Auth token** | `device_token` | Sent as the `x-device-token` header on every C# API call. Required in `live` mode. Stays only in your local `config.json` (out of git). |
| **Action** | `mode` | `"replay"` = fixtures, no hardware · `"live"` = talk to the real board. |

## Source of truth — 2 files
The agent never invents wiring or registers. It reads these two files, and nothing
else defines the hardware:

| File | `config.json` key | Holds |
|---|---|---|
| **settings.json** | `catalog_path` | Register catalog: alias → address, and type (Q15.16 / float / uint32). |
| **topology.yaml** | `topology_path` | The datapath: fixed wiring + selectors (muxes), used for signal-path questions. |

In `live` mode, point `catalog_path` at your **real** settings.json, not the sample.
Both files stay local / out of git.

## 2. Start opencode
From the project folder:
```
cd ask_my_fpga
opencode
```
opencode auto-loads `AGENTS.md` (read rules) and `WRITE_AGENTS.md` (write rules),
and only allows running the `tools/` and `write_tools/` scripts — nothing else.

## 3. Try it with no hardware (replay mode)
Set `"mode": "replay"` in `config.json` to run against the bundled fixtures. This
is the safest way to learn the loop. Then ask, for example:
- "List the FPGA modules."
- "What is PI_SET_KP?"

## 4. Connect to the real board (live mode)
Set `"mode": "live"` and a real `base_url` + `catalog_path` in `config.json`.
Confirm the server first: "Run a status check." (uses `get_status.py`).

## 5. Asking questions (read — always safe)
Reading never changes the hardware. Example prompts:
- "What is the signal path to DAC0?"
- "Which modules can affect DAC0?"
- "Which parameters affect DAC0?"
- "What is the value of GAIN0_GAIN?"
- "Capture DAC0 and tell me the RMS and dominant frequency."
- "Why does SCOPE0 look noisy?" (the agent reports observations first, then
  possible causes as interpretation — it will not guess a cause as fact.)

Every answer is tagged: `fact` (read live), `config` (from the catalog),
`measurement` (computed from samples), or `unknown`.

## 6. Configuring the FPGA (write — approval required)
Writes change live routing and outputs, so the agent always follows
**dry-run → show → confirm → apply**:
1. You ask for a change ("Route ASG1 through the chain to DAC0").
2. The agent runs a **dry run** and shows exactly which registers change
   (current → new).
3. **You approve.** Only then does it re-run with `--apply`.
4. It reports read-back `verified: true/false` for each write.

Example prompts:
- "Route ASG1 to DAC0." → the agent checks feasibility, shows the mux writes,
  waits for your OK, then applies.
- "Set GAIN0_GAIN to 1.5."
- "Generate a 1 kHz sine, 0.2 V amplitude, on ASG1."
- "Set SCOPE0 to tap LPF2 and start acquisition."

If a change is impossible (e.g. a scope can't tap that node), the agent says so
and, when there is one, suggests the workaround.

## 7. Stopping a signal
- "Stop ASG1." / "Disable the generator on ASG1."
- "Stop SCOPE0 acquisition."

## 8. Safety notes
- Rerouting a live signal can interrupt a running lock or experiment. The dry run
  shows the routing you would overwrite — read it before approving.
- The agent never applies a write without your explicit approval in that message.
- Only values allowed by the topology and register catalog are writable.

## 9. Language note
Say "日本語で答えて" (answer in Japanese) or just start writing in Japanese and the
agent switches. Register names, module names, and numbers stay in their original
form in both languages.
