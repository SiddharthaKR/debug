#!/usr/bin/env python3
"""Static metadata for one register/alias from the catalog. kind=config (or unknown)."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="alias/register name, e.g. PI_SET_KP")
    a = ap.parse_args()
    cfg = fc.load_config(); cat = fc.load_catalog(cfg)
    meta = cat["meta"].get(a.name, {})
    r = fc.resolve_alias(a.name, cat)
    if not r["ok"]:
        fc.emit(fc.tagged(fc.UNKNOWN, register=a.name,
                          module=a.name.split("_")[0], reason=r["reason"], **meta))
        return
    addr = r["address"]
    fc.emit(fc.tagged(fc.CONFIG, register=a.name, module=a.name.split("_")[0],
                      address=addr, type=meta.get("type"), format=meta.get("format"),
                      default=meta.get("default"),
                      aliases_sharing_address=cat["overlaps"].get(addr)))

if __name__ == "__main__":
    main()
