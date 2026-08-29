#!/usr/bin/env python3
"""Curated per-module snapshot of live register values. kind=fact.
Curate via config.state_registers = {"PI": ["PI_SET_KP", ...], ...};
otherwise defaults to the catalog's typed registers per module."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modules", help="comma-separated subset, e.g. PI,MIX")
    a = ap.parse_args()
    cfg = fc.load_config(); cat = fc.load_catalog(cfg)
    sel = cfg.get("state_registers")
    mods = a.modules.split(",") if a.modules else sorted(cat["modules"])
    state, unknown = {}, []
    for m in mods:
        if sel and m in sel:
            names = sel[m]
        else:
            names = [n for n in cat["modules"].get(m, []) if n in cat["meta"]]
        md = {}
        for n in names:
            r = fc.resolve_alias(n, cat)
            if not r["ok"]:
                unknown.append({"register": n, "reason": r["reason"]}); continue
            rd = fc.read_register(r["address"], cfg)
            if not rd["ok"]:
                unknown.append({"register": n, "address": r["address"],
                                "reason": rd["reason"]}); continue
            md[n] = fc.decode_value(rd["raw"], cat["meta"].get(n))
        state[m] = md
    fc.emit(fc.tagged(fc.FACT, device=fc.resolve_device_id(cfg), modules=state,
                      unknown=unknown,
                      note="values decoded per catalog format; curate via config.state_registers"))

if __name__ == "__main__":
    main()
