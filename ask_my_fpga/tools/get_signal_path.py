#!/usr/bin/env python3
"""Trace the live signal path upstream of a node (e.g. DAC0, SCOPE0).
Fixed wires are tagged config (documented); mux selectors are read live and
tagged fact. Each on-path selector also reports the alternatives it could select.
Answers: 'signal path to DAC0' and 'what modules can affect DAC0'."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc
import topology as tp

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="node to trace upstream from, e.g. DAC0 / SCOPE0")
    a = ap.parse_args()
    cfg = fc.load_config(); cat = fc.load_catalog(cfg); topo = tp.load_topology(cfg)
    if a.target not in topo["nodes"]:
        fc.emit(fc.tagged(fc.UNKNOWN, target=a.target,
                          reason="'%s' is not a node in the topology" % a.target,
                          known_nodes=sorted(topo["nodes"]))); return
    edges, nodes = tp.walk_upstream(a.target, topo, cfg, cat)
    live = any(e.get("via") == "selector" and e["provenance"] == fc.FACT for e in edges)
    fc.emit(fc.tagged(fc.FACT if live else fc.CONFIG,
                      target=a.target,
                      upstream_nodes=sorted(n for n in nodes if n != a.target),
                      path=edges,
                      note="path built from live selector reads (fact) + documented "
                           "fixed wiring (config); 'alternatives' = other sources each "
                           "mux on the path could select"))

if __name__ == "__main__":
    main()
