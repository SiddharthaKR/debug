#!/usr/bin/env python3
"""List the parameters that can affect a node's signal: for every module on the
live upstream path, the config registers from the catalog. kind=config.
Causal claims ('this one is making it noisy') are INTERPRETATION, not stated here."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc
import topology as tp

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="e.g. DAC0")
    a = ap.parse_args()
    cfg = fc.load_config(); cat = fc.load_catalog(cfg); topo = tp.load_topology(cfg)
    if a.target not in topo["nodes"]:
        fc.emit(fc.tagged(fc.UNKNOWN, target=a.target,
                          reason="'%s' is not a node in the topology" % a.target)); return
    _, nodes = tp.walk_upstream(a.target, topo, cfg, cat)
    by_node = {}
    for n in sorted(nodes):
        pfx = (topo["nodes"].get(n) or {}).get("params_prefix")
        if not pfx:
            continue
        regs = sorted(al for al in cat["aliases"]
                      if al == pfx or al.startswith(pfx + "_") or al.split("_")[0] == pfx)
        if regs:
            by_node[n] = regs
    fc.emit(fc.tagged(fc.CONFIG, target=a.target,
                      affecting_parameters=by_node,
                      note="registers of every module on the upstream path; which one "
                           "explains an observed signal is interpretation, verify by reading values"))

if __name__ == "__main__":
    main()
