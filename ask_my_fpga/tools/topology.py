"""Load the datapath topology and walk it, resolving mux selectors against live
register reads. Fixed edges = documented wiring (config); selector edges = live
(fact). Every wire is classified exactly once."""
import os, yaml
import fpga_common as fc

def load_topology(cfg):
    path = cfg.get("topology_path")
    if path and not os.path.isabs(path):
        path = os.path.join(cfg["_root"], path)
    t = yaml.safe_load(open(path))
    fixed_in = {}
    for e in t.get("fixed_edges", []):
        fixed_in.setdefault(e[1], []).append(e[0])
    sel_in = {}
    for s in t.get("selectors", []):
        sel_in.setdefault(s["dest"], []).append({
            "register": s["register"],
            "field": s.get("field"),
            "sources": {int(k): v for k, v in (s.get("sources") or {}).items()},
        })
    return {"nodes": t.get("nodes", {}), "fixed_in": fixed_in, "sel_in": sel_in}

def _sel_value(raw, field):
    v = raw & 0xFFFFFFFF
    if field:  # "[hi:lo]"
        hi, lo = [int(x) for x in field.strip("[]").split(":")]
        v = (v >> lo) & ((1 << (hi - lo + 1)) - 1)
    return v

def upstream_hops(node, topo, cfg, cat):
    """One hop upstream of `node`: list of {from, via, provenance, ...}."""
    hops = []
    for src in topo["fixed_in"].get(node, []):
        hops.append({"from": src, "via": "fixed", "provenance": fc.CONFIG})
    for sel in topo["sel_in"].get(node, []):
        reg = sel["register"]; opts = sorted(set(sel["sources"].values()))
        r = fc.resolve_alias(reg, cat)
        if not r["ok"]:
            hops.append({"from": None, "via": "selector", "register": reg,
                         "provenance": fc.UNKNOWN, "reason": r["reason"], "options": opts}); continue
        rd = fc.read_register(r["address"], cfg)
        if not rd["ok"]:
            hops.append({"from": None, "via": "selector", "register": reg,
                         "provenance": fc.UNKNOWN, "reason": rd["reason"], "options": opts}); continue
        val = _sel_value(rd["raw"], sel["field"])
        src = sel["sources"].get(val, "UNKNOWN")
        hops.append({"from": src, "via": "selector", "register": reg, "value": val,
                     "provenance": fc.FACT if src != "UNKNOWN" else fc.UNKNOWN,
                     "alternatives": sorted(v for k, v in sel["sources"].items() if k != val)})
    return hops

def walk_upstream(target, topo, cfg, cat, max_depth=40):
    edges, nodes, seen = [], {target}, set()
    stack = [(target, 0)]
    while stack:
        node, d = stack.pop()
        if node in seen or d > max_depth:
            continue
        seen.add(node)
        for h in upstream_hops(node, topo, cfg, cat):
            e = {"to": node}; e.update(h)
            edges.append(e)
            src = h.get("from")
            if src and src not in seen and src in topo["nodes"]:
                nodes.add(src); stack.append((src, d + 1))
            elif src:
                nodes.add(src)
    return edges, nodes
