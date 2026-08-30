#!/usr/bin/env python3
"""What CAN be routed to a node (topology only - no hardware, no writes).
  get_reachable.py DAC0            -> sources routable to DAC0 + direct mux options
  get_reachable.py SCOPE0 --source PI0  -> is PI0 routable to SCOPE0, and the exact
                                           selector writes that would do it
kind=config."""
import argparse, os, sys
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc
import topology as tp

def possible_in(node, topo):
    outs = [(s, None, None) for s in topo["fixed_in"].get(node, [])]
    for sel in topo["sel_in"].get(node, []):
        for val, src in sel["sources"].items():
            outs.append((src, sel["register"], val))
    return outs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--source")
    a = ap.parse_args()
    cfg = fc.load_config(); topo = tp.load_topology(cfg)
    if a.target not in topo["nodes"]:
        fc.emit(fc.tagged(fc.UNKNOWN, target=a.target, reason="unknown node")); return
    reach = {a.target}; parent = {}
    dq = deque([a.target])
    while dq:
        n = dq.popleft()
        for src, reg, val in possible_in(n, topo):
            if src not in reach:
                reach.add(src); parent[src] = (n, reg, val); dq.append(src)
    srcs = sorted(s for s in reach if s != a.target and not possible_in(s, topo))
    direct = {sel["register"]: sorted(set(sel["sources"].values()))
              for sel in topo["sel_in"].get(a.target, [])}
    if a.source:
        if a.source not in reach:
            fc.emit(fc.tagged(fc.UNKNOWN, target=a.target, source=a.source, routable=False,
                              reason="%s cannot be routed to %s by any mux setting" % (a.source, a.target),
                              routable_sources=srcs)); return
        path, writes, node = [], [], a.source
        while node != a.target:
            nxt, reg, val = parent[node]
            if reg is not None:
                writes.append({"register": reg, "set_value": val, "routes": "%s -> %s" % (node, nxt)})
            path.append(node); node = nxt
        path.append(a.target)
        fc.emit(fc.tagged(fc.CONFIG, target=a.target, source=a.source, routable=True,
                          path=path, required_writes=writes,
                          note="apply these with set_signal_path (dry-run first)"))
        return
    fc.emit(fc.tagged(fc.CONFIG, target=a.target, directly_selectable=direct,
                      all_routable_sources=srcs,
                      note="sources routable to target via mux settings; --source X gives the exact writes"))

if __name__ == "__main__":
    main()
