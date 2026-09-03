#!/usr/bin/env python3
"""Ask My FPGA - engineering operations behind the MCP server.

Pure operation functions (no MCP dependency, so they are unit-testable). Every
function returns a JSON-able dict carrying a `kind` tag (fact/config/measurement/
unknown). Secrets (x-device-token, deviceId) come from config.json via
fpga_common and are NEVER parameters here. All heavy logic is imported from the
existing tools - this module only composes and formats.

Writes are two-phase:
  plan_*        -> read current state, compute the exact register diff, return a
                   plan_token (nothing is written).
  commit_write  -> re-read hardware, ABORT if state moved since the plan, then
                   apply and read-back verify.
"""
import os, sys, time, secrets
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "write_tools"))

import fpga_common as fc          # config, catalog resolve/decode/encode, HTTP, RMW
import topology as tp             # load_topology, walk_upstream, _sel_value
from get_reachable import possible_in          # topology reachability primitive
from set_parameter import build as _param_plan  # name+value -> register plan
from set_signal_path import plan_hop as _path_plan  # hop -> selector write plan
import capture_analyze_signal as cap            # capture_ws/load_replay/analyze

FACT, CONFIG, MEAS, UNKNOWN = fc.FACT, fc.CONFIG, fc.MEASUREMENT, fc.UNKNOWN
def tagged(kind, **kw):
    return fc.tagged(kind, **kw)

# ---------------- plan store (in-memory, per server process) ----------------
_PLANS = {}
_TTL = 300  # seconds a plan_token stays valid

def _store(op, writes):
    tok = "plan_" + secrets.token_hex(6)
    _PLANS[tok] = {"op": op, "writes": writes, "ts": time.time()}
    return tok

# =========================== READ operations ===============================
def get_status():
    """Connectivity / status snapshot from the SharpRPL server (GET /api/status).
    Run this first to confirm the app is reachable. kind=fact."""
    c = fc.load_config()
    try:
        return tagged(FACT, endpoint="status", base_url=c.get("base_url"),
                      data=fc.call_api(c, "status"))
    except Exception as e:  # noqa
        return tagged(UNKNOWN, endpoint="status", base_url=c.get("base_url"), reason=str(e))

def get_modules():
    """List the FPGA modules known to the register catalog. kind=config."""
    c = fc.load_config(); cat = fc.load_catalog(c)
    counts = {m: len(rs) for m, rs in sorted(cat["modules"].items())}
    gens = sorted((c.get("asg_channel_map") or {}).keys())
    return tagged(CONFIG, modules=sorted(counts), register_counts=counts,
                  generators=gens, source=os.path.basename(c["catalog_path"]),
                  note="'modules' are register-catalog blocks; 'generators' (ASG0/ASG1) are "
                       "signal-generator OUTPUTS configured via configure_asg/plan_configure_asg "
                       "- not catalog modules, and they have no registers here")

def get_parameter(name):
    """Read one named parameter live and decode it to engineering units
    (e.g. PI_SET_KP -> -0.125). Use the semantic alias, never an address.
    kind=fact (or unknown)."""
    c = fc.load_config(); cat = fc.load_catalog(c)
    r = fc.resolve_alias(name, cat)
    if not r["ok"]:
        return tagged(UNKNOWN, parameter=name, reason=r["reason"])
    rd = fc.read_register(r["address"], c)
    entry = cat["meta"].get(name, {})
    if not rd["ok"]:
        return tagged(UNKNOWN, parameter=name, address=r["address"], reason=rd["reason"])
    return tagged(FACT, parameter=name, module=name.split("_")[0],
                  value=fc.decode_value(rd["raw"], entry),
                  raw_hex="0x%08X" % (rd["raw"] & 0xFFFFFFFF), raw_int=rd["raw"],
                  address=r["address"], type=entry.get("type"), format=entry.get("format"))

def get_register_info(name):
    """Static catalog metadata for one named parameter/register (type, format,
    default, address, any aliases sharing its address). kind=config (or unknown)."""
    c = fc.load_config(); cat = fc.load_catalog(c)
    meta = cat["meta"].get(name, {}); r = fc.resolve_alias(name, cat)
    if not r["ok"]:
        return tagged(UNKNOWN, register=name, module=name.split("_")[0], reason=r["reason"], **meta)
    return tagged(CONFIG, register=name, module=name.split("_")[0], address=r["address"],
                  type=meta.get("type"), format=meta.get("format"), default=meta.get("default"),
                  aliases_sharing_address=cat["overlaps"].get(r["address"]))

def get_fpga_state(modules=None):
    """Curated per-module snapshot of live values, decoded to engineering units.
    `modules` = optional comma list (e.g. "PI,MIX"); default all. kind=fact."""
    c = fc.load_config(); cat = fc.load_catalog(c)
    sel = c.get("state_registers")
    mods = [m.strip() for m in modules.split(",")] if modules else sorted(cat["modules"])
    state, unknown = {}, []
    for m in mods:
        names = sel[m] if (sel and m in sel) else [n for n in cat["modules"].get(m, []) if n in cat["meta"]]
        md = {}
        for n in names:
            r = fc.resolve_alias(n, cat)
            if not r["ok"]:
                unknown.append({"register": n, "reason": r["reason"]}); continue
            rd = fc.read_register(r["address"], c)
            if not rd["ok"]:
                unknown.append({"register": n, "address": r["address"], "reason": rd["reason"]}); continue
            md[n] = fc.decode_value(rd["raw"], cat["meta"].get(n))
        state[m] = md
    return tagged(FACT, device=fc.resolve_device_id(c), modules=state, unknown=unknown)

def get_output_status():
    """Live generator/output status for the active device. kind=fact."""
    c = fc.load_config()
    try:
        return tagged(FACT, endpoint="output_status", device=fc.resolve_device_id(c),
                      data=fc.call_api(c, "output_status", device=True))
    except Exception as e:  # noqa
        return tagged(UNKNOWN, endpoint="output_status", reason=str(e))

def get_sessions():
    """Registered device sessions + the active device. kind=fact."""
    c = fc.load_config()
    try:
        return tagged(FACT, endpoint="sessions", data=fc.call_api(c, "sessions"))
    except Exception as e:  # noqa
        return tagged(UNKNOWN, endpoint="sessions", reason=str(e))

def get_signal_path(target):
    """Trace the live signal path upstream of a node (e.g. DAC0, SCOPE0). Fixed
    wiring = config; live mux selectors = fact; each mux also lists the
    alternatives it could select. Answers 'signal path to X' and 'what can affect
    X'. kind=fact (or config if no live selectors on the path)."""
    c = fc.load_config(); cat = fc.load_catalog(c); topo = tp.load_topology(c)
    if target not in topo["nodes"]:
        return tagged(UNKNOWN, target=target, reason="'%s' is not a node in the topology" % target,
                      known_nodes=sorted(topo["nodes"]))
    edges, nodes = tp.walk_upstream(target, topo, c, cat)
    live = any(e.get("via") == "selector" and e["provenance"] == FACT for e in edges)
    return tagged(FACT if live else CONFIG, target=target,
                  upstream_nodes=sorted(n for n in nodes if n != target), path=edges,
                  note="live selector reads (fact) + documented fixed wiring (config); "
                       "'alternatives' = other sources each mux could select")

def get_affecting_parameters(target):
    """For every module on the live upstream path of `target`, list its config
    registers. Which one explains an observed signal is INTERPRETATION, not stated
    here. kind=config."""
    c = fc.load_config(); cat = fc.load_catalog(c); topo = tp.load_topology(c)
    if target not in topo["nodes"]:
        return tagged(UNKNOWN, target=target, reason="'%s' is not a node in the topology" % target)
    _, nodes = tp.walk_upstream(target, topo, c, cat)
    by_node = {}
    for n in sorted(nodes):
        pfx = (topo["nodes"].get(n) or {}).get("params_prefix")
        if not pfx:
            continue
        regs = sorted(al for al in cat["aliases"]
                      if al == pfx or al.startswith(pfx + "_") or al.split("_")[0] == pfx)
        if regs:
            by_node[n] = regs
    return tagged(CONFIG, target=target, affecting_parameters=by_node,
                  note="registers of every module on the upstream path; verify by reading values")

def get_reachable(target, source=None):
    """Feasibility (topology only, no writes): what sources CAN be routed to
    `target`. With `source`, reports whether it is routable and the exact selector
    writes that would do it. Use before planning a route. kind=config."""
    c = fc.load_config(); topo = tp.load_topology(c)
    if target not in topo["nodes"]:
        return tagged(UNKNOWN, target=target, reason="unknown node")
    reach = {target}; parent = {}; dq = deque([target])
    while dq:
        n = dq.popleft()
        for src, reg, val in possible_in(n, topo):
            if src not in reach:
                reach.add(src); parent[src] = (n, reg, val); dq.append(src)
    srcs = sorted(s for s in reach if s != target and not possible_in(s, topo))
    direct = {sel["register"]: sorted(set(sel["sources"].values()))
              for sel in topo["sel_in"].get(target, [])}
    if source:
        if source not in reach:
            return tagged(UNKNOWN, target=target, source=source, routable=False,
                          reason="%s cannot be routed to %s by any mux setting" % (source, target),
                          routable_sources=srcs)
        path, writes, node = [], [], source
        while node != target:
            nxt, reg, val = parent[node]
            if reg is not None:
                writes.append({"register": reg, "set_value": val, "routes": "%s -> %s" % (node, nxt)})
            path.append(node); node = nxt
        path.append(target)
        return tagged(CONFIG, target=target, source=source, routable=True, path=path,
                      required_writes=writes, note="apply with plan_set_signal_path then commit_write")
    return tagged(CONFIG, target=target, directly_selectable=direct, all_routable_sources=srcs,
                  note="sources routable to target via mux settings; pass source= for exact writes")

def capture_analyze_signal(signal="scope", channel=None, nsamples=16384):
    """Capture from /ws/wave and return a SCALAR summary only (RMS, mean/DC, peak,
    min, max, dominant frequency, top FFT peaks, clipping) - never the raw samples.
    kind=measurement (or unknown)."""
    c = fc.load_config()
    try:
        if c["mode"] == "replay":
            counts, dec = cap.load_replay(c, channel)
        else:
            counts, dec = cap.capture_ws(c, channel, nsamples)
    except Exception as e:  # noqa
        return tagged(UNKNOWN, signal=signal, reason="capture failed: %s" % e)
    out = cap.analyze(counts, dec, c); out["signal"] = signal
    return out

# =========================== WRITE planning ================================
def plan_set_parameters(parameters):
    """Plan writing one or more named module parameters in ENGINEERING UNITS,
    e.g. {"PI0_SET_KP": 0.5, "GAIN0_GAIN": 1.5}. Reads current values, computes
    the register diff, returns a plan_token. Nothing is written until
    commit_write(plan_token). Refuses bit-packed/shared-address registers."""
    c = fc.load_config(); cat = fc.load_catalog(c)
    if not parameters:
        return tagged(UNKNOWN, reason="no parameters given")
    disp, writes, errors = [], [], []
    for name, value in parameters.items():
        try:
            value = float(value)
        except (TypeError, ValueError):
            errors.append({"register": name, "error": "value not numeric"}); continue
        b = _param_plan(name, value, cat, c)
        if "error" in b:
            errors.append(b); continue
        rd = fc.read_register(b["address"], c)
        if not rd["ok"]:
            errors.append({"register": name, "error": "pre-read failed: %s" % rd["reason"]}); continue
        writes.append({"type": "reg", "label": name, "address": b["address"],
                       "planned_current_raw": rd["raw"] & 0xFFFFFFFF, "new_raw": b["raw"],
                       "new_value": value, "entry": cat["meta"].get(name, {})})
        disp.append({"register": name, "current": b["current_value"], "new": value, "raw_hex": b["raw_hex"]})
    if errors:
        return tagged(UNKNOWN, action="plan_set_parameters", errors=errors, note="fix these; nothing planned")
    tok = _store("set_parameters", writes)
    return tagged(CONFIG, action="plan_set_parameters", dry_run=True, changes=disp,
                  plan_token=tok, note="review, then commit_write(plan_token) - each read-back verified")

def plan_set_signal_path(nodes):
    """Plan a signal route by setting mux selectors. `nodes` = the path in
    signal-flow order SOURCE..SINK, e.g. ["ASG1","LPF1","GAIN0","DAC0"]. Inverts
    the topology into the exact selector writes and reads current routing. Fixed
    hops need no write. Returns a plan_token; nothing changes until commit_write."""
    c = fc.load_config(); cat = fc.load_catalog(c); topo = tp.load_topology(c)
    nodes = [str(n) for n in nodes]
    bad = [n for n in nodes if n not in topo["nodes"]]
    if bad:
        return tagged(UNKNOWN, reason="unknown nodes: %s" % bad, known_nodes=sorted(topo["nodes"]))
    hops = [_path_plan(s, d, topo, cat, c) for s, d in zip(nodes, nodes[1:])]
    errs = [h for h in hops if "error" in h]
    if errs:
        return tagged(UNKNOWN, action="plan_set_signal_path", path=nodes, plan=hops,
                      reason="path not achievable", hint="use get_reachable for a valid route")
    writes, disp = [], []
    for h in hops:
        if h.get("via") != "selector":
            continue
        rd = fc.read_register(h["address"], c)
        if not rd["ok"]:
            return tagged(UNKNOWN, reason="pre-read failed for %s: %s" % (h["register"], rd["reason"]))
        writes.append({"type": "field", "register": h["register"], "address": h["address"],
                       "field": h["field"], "planned_current_field": tp._sel_value(rd["raw"], h["field"]),
                       "set_value": h["set_value"], "route": "%s->%s" % (h["src"], h["dst"])})
        disp.append({"register": h["register"], "field": h["field"], "current": h.get("current_source"),
                     "new": h["src"], "set_value": h["set_value"]})
    if not writes:
        return tagged(CONFIG, action="plan_set_signal_path", path=nodes, writes=[],
                      note="entire path is hardwired - no selector writes needed")
    tok = _store("set_signal_path", writes)
    return tagged(CONFIG, action="plan_set_signal_path", dry_run=True, path=nodes, writes=disp,
                  plan_token=tok, note="review, then commit_write(plan_token) - RMW + read-back verify")

def plan_configure_asg(asg, waveform="SINE", freq_hz=1000.0, amplitude_vpp=1.0, offset_v=0.0, enabled=True):
    """Plan an ASG (signal generator) output: waveform, frequency (Hz), amplitude
    (Vpp), offset (V), enabled. Returns a plan_token; commit_write applies it via
    the output API and reads back status."""
    c = fc.load_config(); ch = (c.get("asg_channel_map") or {"ASG0": 1, "ASG1": 2}).get(asg)
    if ch is None:
        return tagged(UNKNOWN, asg=asg, reason="no channel mapping (config.asg_channel_map)")
    body = {"waveform": str(waveform).upper(), "frequencyHz": freq_hz, "amplitudeVpp": amplitude_vpp,
            "offsetV": offset_v, "enabled": bool(enabled)}
    tok = _store("configure_asg", [{"type": "output_configure", "channel": ch, "body": body}])
    return tagged(CONFIG, action="plan_configure_asg", asg=asg, channel=ch, planned=body,
                  dry_run=True, plan_token=tok, note="review, then commit_write(plan_token)")

def plan_stop_asg(asg):
    """Plan stopping an ASG output (dedicated stop endpoint). commit_write performs it."""
    c = fc.load_config(); ch = (c.get("asg_channel_map") or {"ASG0": 1, "ASG1": 2}).get(asg)
    if ch is None:
        return tagged(UNKNOWN, asg=asg, reason="no channel mapping (config.asg_channel_map)")
    tok = _store("stop_asg", [{"type": "output_stop", "channel": ch}])
    return tagged(CONFIG, action="plan_stop_asg", asg=asg, channel=ch, dry_run=True,
                  plan_token=tok, note="review, then commit_write(plan_token) to STOP this output")

def plan_configure_scope(scope, source=None, decimation=None, acquisition=None):
    """Plan scope config: `source` = signal it taps (a SCOPE_SEL option),
    `decimation` = sample-rate divider (125MHz/decimation), `acquisition` =
    'start' or 'stop'. Returns a plan_token; commit_write applies."""
    c = fc.load_config(); cat = fc.load_catalog(c); topo = tp.load_topology(c)
    if scope not in topo["nodes"]:
        return tagged(UNKNOWN, scope=scope, reason="unknown node")
    writes, disp, errors = [], {"scope": scope}, []
    if source:
        sels = topo["sel_in"].get(scope, [])
        if not sels:
            errors.append("%s has no selector (cannot set its tap)" % scope)
        else:
            sel = sels[0]; inv = {v: k for k, v in sel["sources"].items()}
            if source not in inv:
                errors.append("%s cannot tap %s; options: %s" % (scope, source, sorted(inv)))
            else:
                r = fc.resolve_alias(sel["register"], cat)
                if not r["ok"]:
                    errors.append("register %s not in catalog" % sel["register"])
                else:
                    rd = fc.read_register(r["address"], c)
                    if not rd["ok"]:
                        errors.append("pre-read failed for %s" % sel["register"])
                    else:
                        curf = tp._sel_value(rd["raw"], sel.get("field"))
                        writes.append({"type": "field", "register": sel["register"], "address": r["address"],
                                       "field": sel.get("field"), "planned_current_field": curf,
                                       "set_value": inv[source], "route": "%s->%s" % (source, scope)})
                        disp["tap"] = {"register": sel["register"], "current": sel["sources"].get(curf, "?"),
                                       "new": source, "set_value": inv[source]}
    if decimation is not None:
        if int(decimation) < 1:
            errors.append("decimation must be >= 1")
        else:
            writes.append({"type": "acq_decimation", "n": int(decimation)}); disp["decimation"] = int(decimation)
            if int(decimation) not in (1, 8, 64, 1024, 8192, 65536):
                disp["decimation_note"] = "non-standard Red Pitaya decimation (usual: 1,8,64,1024,8192,65536)"
    if acquisition:
        if acquisition not in ("start", "stop"):
            errors.append("acquisition must be 'start' or 'stop'")
        else:
            writes.append({"type": "acq_control", "which": acquisition}); disp["acquisition"] = acquisition
    if errors:
        return tagged(UNKNOWN, action="plan_configure_scope", scope=scope, errors=errors,
                      hint="get_reachable('%s') shows valid tap sources" % scope)
    if not writes:
        return tagged(UNKNOWN, scope=scope, reason="nothing to do (give source / decimation / acquisition)")
    tok = _store("configure_scope", writes)
    disp["dry_run"] = True; disp["plan_token"] = tok
    disp["note"] = "review, then commit_write(plan_token)"
    return tagged(CONFIG, action="plan_configure_scope", **disp)

# =========================== COMMIT =========================================
def commit_write(plan_token):
    """Apply a previously planned write. Re-reads hardware and ABORTS (writing
    nothing) if any register moved since the plan, then applies and read-back
    verifies. Call ONLY after a human has reviewed the matching plan_* output and
    approved it. kind=fact (or unknown if aborted)."""
    p = _PLANS.get(plan_token)
    if not p:
        return tagged(UNKNOWN, reason="unknown or expired plan_token; re-plan")
    if time.time() - p["ts"] > _TTL:
        _PLANS.pop(plan_token, None)
        return tagged(UNKNOWN, reason="plan expired (>%ds); re-plan" % _TTL)
    c = fc.load_config(); writes = p["writes"]
    # 1) integrity: re-verify current state for register/field writes before touching anything
    drift = []
    for w in writes:
        if w["type"] in ("reg", "field"):
            rd = fc.read_register(w["address"], c)
            if not rd["ok"]:
                drift.append({"register": w.get("label") or w.get("register"), "reason": rd["reason"]}); continue
            if w["type"] == "reg" and (rd["raw"] & 0xFFFFFFFF) != w["planned_current_raw"]:
                drift.append({"register": w["label"], "planned_current": "0x%08X" % w["planned_current_raw"],
                              "now": "0x%08X" % (rd["raw"] & 0xFFFFFFFF)})
            elif w["type"] == "field":
                cur = tp._sel_value(rd["raw"], w["field"])
                if cur != w["planned_current_field"]:
                    drift.append({"register": w["register"], "planned_current": w["planned_current_field"], "now": cur})
    if drift:
        return tagged(UNKNOWN, action="commit_write", op=p["op"], aborted=True,
                      reason="hardware state changed since plan - nothing written",
                      drift=drift, hint="re-run the matching plan_* and review again")
    # 2) apply
    results = []
    for w in writes:
        if w["type"] == "reg":
            wr = fc.write_register(c, w["address"], w["new_raw"])
            if not wr["ok"]:
                results.append({"target": w["label"], "ok": False, "reason": wr["reason"]}); continue
            rb = fc.read_register(w["address"], c); got = (rb["raw"] & 0xFFFFFFFF) if rb["ok"] else None
            results.append({"target": w["label"], "new": w["new_value"], "raw_hex": "0x%08X" % w["new_raw"],
                            "readback_value": (fc.decode_value(got, w["entry"]) if got is not None else None),
                            "verified": bool(got == w["new_raw"])})
        elif w["type"] == "field":
            wf = fc.write_field(c, w["address"], w["field"], w["set_value"])
            results.append({"target": w["register"], "routed": w.get("route"),
                            **{k: wf.get(k) for k in ("ok", "old_raw", "new_raw", "readback", "verified", "reason")}})
        elif w["type"] == "output_configure":
            r = fc.configure_output(c, w["channel"], w["body"])
            results.append({"target": "ASG ch%s" % w["channel"], "ok": r["ok"], "applied": w["body"],
                            **({"reason": r.get("reason")} if not r["ok"] else {})})
        elif w["type"] == "output_stop":
            r = fc.output_stop(c, w["channel"])
            results.append({"target": "ASG ch%s stop" % w["channel"], "ok": r["ok"],
                            **({"reason": r.get("reason")} if not r["ok"] else {})})
        elif w["type"] == "acq_decimation":
            r = fc.acq_decimation(c, w["n"]); results.append({"target": "decimation", "ok": r["ok"], "decimation": w["n"]})
        elif w["type"] == "acq_control":
            r = fc.acq_control(c, w["which"]); results.append({"target": "acquisition", "ok": r["ok"], "acquisition": w["which"]})
    _PLANS.pop(plan_token, None)
    all_ok = all(r.get("verified", r.get("ok")) for r in results)
    return tagged(FACT, action="commit_write", op=p["op"], applied=results, all_verified=bool(all_ok))

# tool groups (used by server.py to register with the right annotations)
READ_OPS = [get_status, get_modules, get_parameter, get_register_info, get_fpga_state,
            get_output_status, get_sessions, get_signal_path, get_affecting_parameters,
            get_reachable, capture_analyze_signal]
PLAN_OPS = [plan_set_parameters, plan_set_signal_path, plan_configure_asg, plan_stop_asg,
            plan_configure_scope]
COMMIT_OP = commit_write
