#!/usr/bin/env python3
"""Validate topology.yaml against the register catalog: every selector register
must resolve, and every params_prefix should match some catalog register.
Run this after (re)generating the topology so name drift fails loudly."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc
import topology as tp

def main():
    cfg = fc.load_config(); cat = fc.load_catalog(cfg); topo = tp.load_topology(cfg)
    problems = []
    # selector registers must resolve in the catalog
    for dest, sels in topo["sel_in"].items():
        for s in sels:
            if not fc.resolve_alias(s["register"], cat)["ok"]:
                problems.append("selector register '%s' (dest %s) not in catalog" % (s["register"], dest))
    # every selector source + fixed src/dst must be a known node
    known = set(topo["nodes"])
    for dest, sels in topo["sel_in"].items():
        for s in sels:
            for v, src in s["sources"].items():
                if src not in known and src != "UNKNOWN":
                    problems.append("selector %s value %s -> unknown node '%s'" % (s["register"], v, src))
    # params_prefix that match no catalog register (warn)
    warns = []
    for n, meta in topo["nodes"].items():
        pfx = (meta or {}).get("params_prefix")
        if pfx and not any(a == pfx or a.startswith(pfx + "_") or a.split("_")[0] == pfx
                           for a in cat["aliases"]):
            warns.append("node '%s' params_prefix '%s' matches no catalog register" % (n, pfx))
    fc.emit(fc.tagged(fc.CONFIG if not problems else fc.UNKNOWN,
                      ok=not problems, problems=problems, warnings=warns,
                      nodes=len(topo["nodes"])))

if __name__ == "__main__":
    main()
