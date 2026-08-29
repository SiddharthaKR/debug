#!/usr/bin/env python3
"""Resolve an alias, read it live, and decode to engineering units. kind=fact (or unknown)."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="alias/register name, e.g. PI_SET_KP")
    a = ap.parse_args()
    cfg = fc.load_config(); cat = fc.load_catalog(cfg)
    r = fc.resolve_alias(a.name, cat)
    if not r["ok"]:
        fc.emit(fc.tagged(fc.UNKNOWN, parameter=a.name, reason=r["reason"]))
        return
    rd = fc.read_register(r["address"], cfg)
    entry = cat["meta"].get(a.name, {})
    if not rd["ok"]:
        fc.emit(fc.tagged(fc.UNKNOWN, parameter=a.name, address=r["address"],
                          reason=rd["reason"]))
        return
    val = fc.decode_value(rd["raw"], entry)
    fc.emit(fc.tagged(fc.FACT, parameter=a.name, module=a.name.split("_")[0],
                      value=val, raw_hex="0x%08X" % (rd["raw"] & 0xFFFFFFFF),
                      raw_int=rd["raw"], address=r["address"],
                      type=entry.get("type"), format=entry.get("format")))

if __name__ == "__main__":
    main()
