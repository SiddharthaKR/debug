#!/usr/bin/env python3
"""WRITE TOOL - configure a signal path by inverting the topology into selector
writes. Dry-run by default; --apply writes each mux as read-modify-write (only
its bit-field) then read-back verifies.
  set_signal_path.py PI0 LPF1 GAIN0 DAC0            (dry run)
  set_signal_path.py PI0 LPF1 GAIN0 DAC0 --apply
Nodes are listed in signal-flow order: SOURCE ... SINK.
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import fpga_common as fc
import topology as tp

def plan_hop(src, dst, topo, cat, cfg):
    if src in topo["fixed_in"].get(dst, []):
        return {"dst": dst, "src": src, "via": "fixed", "action": "none (hardwired)"}
    for sel in topo["sel_in"].get(dst, []):
        inv = {v: k for k, v in sel["sources"].items()}
        if src in inv:
            reg, field = sel["register"], sel.get("field")
            p = {"dst": dst, "src": src, "via": "selector", "register": reg,
                 "field": field, "set_value": inv[src]}
            r = fc.resolve_alias(reg, cat)
            if not r["ok"]:
                p["error"] = "register %s not in catalog" % reg; return p
            p["address"] = r["address"]
            rd = fc.read_register(r["address"], cfg)
            if rd["ok"]:
                cv = tp._sel_value(rd["raw"], field)
                p["current_source"] = sel["sources"].get(cv, "?")
            return p
    return {"dst": dst, "src": src, "error": "%s cannot feed %s (no fixed edge / selector option)" % (src, dst)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nodes", nargs="+", help="path in signal-flow order: SRC ... SINK")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    cfg = fc.load_config(); cat = fc.load_catalog(cfg); topo = tp.load_topology(cfg)
    bad = [n for n in a.nodes if n not in topo["nodes"]]
    if bad:
        fc.emit(fc.tagged(fc.UNKNOWN, reason="unknown nodes: %s" % bad)); return
    plans = [plan_hop(s, d, topo, cat, cfg) for s, d in zip(a.nodes, a.nodes[1:])]
    errors = [p for p in plans if "error" in p]
    writes = [p for p in plans if p.get("via") == "selector"]
    if errors:
        fc.emit(fc.tagged(fc.UNKNOWN, path=a.nodes, plan=plans,
                          reason="path not achievable", hint="use get_reachable for a valid route")); return
    if not a.apply:
        fc.emit(fc.tagged(fc.CONFIG, action="set_signal_path", path=a.nodes, dry_run=True,
                          writes=[{"register": p["register"], "field": p["field"],
                                   "current": p.get("current_source"), "new": p["src"],
                                   "set_value": p["set_value"]} for p in writes],
                          fixed_hops=[p["dst"] for p in plans if p.get("via") == "fixed"],
                          note="DRY RUN - add --apply to write (read-modify-write + read-back verify)")); return
    results = []
    for p in writes:
        wf = fc.write_field(cfg, p["address"], p["field"], p["set_value"])
        results.append({"register": p["register"], "routed": "%s->%s" % (p["src"], p["dst"]),
                        **{k: wf.get(k) for k in ("ok", "old_raw", "new_raw", "readback", "verified", "reason")}})
    fc.emit(fc.tagged(fc.FACT, action="set_signal_path", path=a.nodes,
                      applied=results, all_verified=all(r.get("verified") for r in results)))

if __name__ == "__main__":
    main()
