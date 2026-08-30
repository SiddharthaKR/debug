#!/usr/bin/env python3
"""WRITE TOOL - configure a scope: what it TAPS (SCOPE_SEL register) and/or the
acquisition DECIMATION (sample rate = 125MHz/decimation), plus start/stop.
Dry-run by default; --apply writes (tap = read-modify-write + verify).
  configure_scope.py SCOPE0 --source DAC0
  configure_scope.py SCOPE0 --source DAC0 --decimation 64 --apply
  configure_scope.py SCOPE0 --stop --apply
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import fpga_common as fc
import topology as tp

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scope", help="SCOPE0 or SCOPE1")
    ap.add_argument("--source", help="signal to tap (must be a SCOPE_SEL option)")
    ap.add_argument("--decimation", type=int)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--start", action="store_true")
    g.add_argument("--stop", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    cfg = fc.load_config(); cat = fc.load_catalog(cfg); topo = tp.load_topology(cfg)
    if a.scope not in topo["nodes"]:
        fc.emit(fc.tagged(fc.UNKNOWN, scope=a.scope, reason="unknown node")); return
    plan = {"scope": a.scope}; errors = []; tap = None
    if a.source:
        sels = topo["sel_in"].get(a.scope, [])
        if not sels:
            errors.append("%s has no selector (cannot set its tap)" % a.scope)
        else:
            sel = sels[0]; inv = {v: k for k, v in sel["sources"].items()}
            if a.source not in inv:
                errors.append("%s cannot tap %s; options: %s" % (a.scope, a.source, sorted(inv)))
            else:
                r = fc.resolve_alias(sel["register"], cat)
                if not r["ok"]:
                    errors.append("register %s not in catalog" % sel["register"])
                else:
                    rd = fc.read_register(r["address"], cfg)
                    cur = sel["sources"].get(tp._sel_value(rd["raw"], sel.get("field")), "?") if rd["ok"] else "?"
                    tap = {"register": sel["register"], "field": sel.get("field"), "address": r["address"],
                           "set_value": inv[a.source], "current": cur, "new": a.source}
                    plan["tap"] = {k: tap[k] for k in ("register", "field", "current", "new", "set_value")}
    if a.decimation is not None:
        if a.decimation < 1:
            errors.append("decimation must be >= 1")
        else:
            plan["decimation"] = a.decimation
            if a.decimation not in (1, 8, 64, 1024, 8192, 65536):
                plan["decimation_note"] = "non-standard Red Pitaya decimation (usual: 1,8,64,1024,8192,65536)"
    if a.start: plan["acquisition"] = "start"
    if a.stop: plan["acquisition"] = "stop"
    if errors:
        fc.emit(fc.tagged(fc.UNKNOWN, scope=a.scope, errors=errors,
                          hint="get_reachable %s shows valid tap sources" % a.scope)); return
    if not (a.source or a.decimation is not None or a.start or a.stop):
        fc.emit(fc.tagged(fc.UNKNOWN, scope=a.scope, reason="nothing to do (give --source / --decimation / --start / --stop)")); return
    if not a.apply:
        plan["dry_run"] = True; plan["note"] = "DRY RUN - add --apply to write"
        fc.emit(fc.tagged(fc.CONFIG, action="configure_scope", **plan)); return
    res = {}
    if tap:
        wf = fc.write_field(cfg, tap["address"], tap["field"], tap["set_value"])
        res["tap"] = {"register": tap["register"], "new": tap["new"],
                      **{k: wf.get(k) for k in ("ok", "old_raw", "new_raw", "readback", "verified", "reason")}}
    if a.decimation is not None:
        res["decimation"] = fc.acq_decimation(cfg, a.decimation)
    if a.start: res["acquisition"] = fc.acq_control(cfg, "start")
    if a.stop:  res["acquisition"] = fc.acq_control(cfg, "stop")
    fc.emit(fc.tagged(fc.FACT, action="configure_scope", scope=a.scope, applied=res))

if __name__ == "__main__":
    main()
