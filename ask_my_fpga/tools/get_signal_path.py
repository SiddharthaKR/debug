#!/usr/bin/env python3
"""Read the *_SEL mux/select registers live and, if a mux_map is configured,
resolve them into a signal chain. Without a mux_map the path is UNKNOWN by design
(topology is never invented). kind=fact or unknown."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default=None, help="e.g. DAC0 / SCOPE0")
    a = ap.parse_args()
    cfg = fc.load_config(); cat = fc.load_catalog(cfg)
    sels = sorted(n for n in cat["aliases"] if n.endswith("_SEL"))
    readings = {}
    for n in sels:
        r = fc.resolve_alias(n, cat)
        if not r["ok"]:
            readings[n] = {"kind": fc.UNKNOWN, "reason": r["reason"]}; continue
        rd = fc.read_register(r["address"], cfg)
        readings[n] = (rd["raw"] if rd["ok"]
                       else {"kind": fc.UNKNOWN, "reason": rd["reason"]})
    mux = cfg.get("mux_map")
    if not mux:
        fc.emit(fc.tagged(fc.UNKNOWN, target=a.target, selectors=readings,
                reason="selector->source mapping (config.mux_map) is not configured; "
                       "the routed chain cannot be verified from SEL values alone",
                note="raw *_SEL values above are live facts; add config.mux_map "
                     "{sel_name: {sel_value: source}} to resolve the path"))
        return
    # walk the mux graph from target
    path, node, seen = [a.target], a.target, set()
    while node and node not in seen:
        seen.add(node)
        sel_name = node + "_SEL" if (node + "_SEL") in mux else None
        if not sel_name:
            break
        val = readings.get(sel_name)
        src = mux[sel_name].get(str(val)) if isinstance(val, int) else None
        if src is None:
            break
        path.append(src); node = src
    fc.emit(fc.tagged(fc.FACT, target=a.target, path=list(reversed(path)),
                      selectors=readings))

if __name__ == "__main__":
    main()
