# Ask My FPGA (read-only MVP)

A read-only agent that answers natural-language questions about a Red Pitaya FPGA
by inspecting the live hardware through the existing **SharpRPL C# API** and the
`ntt_qctrl_seeting.json` register catalog. Built to run under a coding-agent
harness (pi.dev or opencode) driving a local LLM (gemma4 via vLLM).

## Layout
```
ask_my_fpga/
  config.json                 # base_url, adc_fullscale_v, device_id, mode, catalog_path
  AGENTS.md                   # instructions the harness loads
  requirements.txt
  tools/
    fpga_common.py            # config, catalog resolve (+unknown-guard), HTTP, decoding
    get_modules.py
    get_register_info.py
    get_parameter.py
    get_fpga_state.py
    get_signal_path.py
    capture_analyze_signal.py
  fixtures/                   # replay data so it runs with no board attached
```

## Configure (`config.json`)
- `mode`: `replay` (fixtures, no hardware) or `live` (talk to the C# API).
- `base_url`: the SharpRPL server, e.g. `http://localhost:5000`.
- `catalog_path`: path to the real `ntt_qctrl_seeting.json` (for live use).
- `adc_fullscale_v`: `1.0` for LV (±1 V), `20.0` for HV.
- `device_id`: pin a device, or `null` to follow `activeDeviceId` from `/api/status`.
- `mux_map` (optional): `{ "NODE_SEL": { "0": "SRC_A", "1": "SRC_B" } }` to let
  `get_signal_path` resolve a chain. Absent → paths are reported as `unknown` by design.
- `state_registers` (optional): `{ "PI": ["PI_SET_KP", ...] }` to curate `get_fpga_state`.

## Run
```
# hardware-free (fixtures)
python3 tools/get_modules.py
python3 tools/get_parameter.py PI_SET_KP
python3 tools/capture_analyze_signal.py DAC0

# live: set "mode":"live" and a real base_url + catalog_path in config.json
```
The five register/topology tools need only the Python standard library. The signal
tool needs `numpy` (and `websocket-client` for live capture): `pip install -r requirements.txt`.

## Safety (v1, no proxy)
Read-only rests on two things, since the C# `memory/write` endpoint is unauthenticated:
1. **No write tool exists** in `tools/`.
2. **Restrict the harness shell** to only these commands. The write endpoint stays
   reachable by raw HTTP, so a general shell would bypass tool-level read-only.
   - opencode: allow bash only for `python3 .../ask_my_fpga/tools/*.py`, deny the rest.
   - pi.dev: use a permission extension to the same effect (or add the read-only
     proxy later to move the guarantee into the transport).

## Wire into the harness
Point the harness at this folder so it loads `AGENTS.md`, and expose the `tools/*.py`
as the only runnable commands. Start in `replay` mode to validate the loop against a
local model, then switch `config.json` to `live`.
