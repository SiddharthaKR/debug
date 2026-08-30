#!/usr/bin/env python3
"""WRITE TOOL - set one or many module registers in engineering units.
Values are NAME=VALUE tokens; set a whole coefficient set at once.
  set_parameter.py PI0_SET_KP=0.5
  set_parameter.py BPF_B0=0.1 BPF_B1=0.2 BPF_B2=0.1 BPF_A1=1.5 BPF_A2=-0.7
  set_parameter.py PI0_SET_KP=0.5 PI0_SET_KI=0.01 PI0_SET_KD=0 --apply
Dry-run by default. Each write is read-back verified; refuses bit-packed
(shared-address) registers since it writes the whole word."""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import fpga_common as fc

def build(name, value, cat, cfg):
    r = fc.resolve_alias(name, cat)
    if not r["ok"]:
        return {"register": name, "error": r["reason"]}
    addr = r["address"]; entry = cat["meta"].get(name, {})
    shared = cat["overlaps"].get(addr)
    if shared and len(shared) > 1:
        return {"register": name, "error": "shares address with %s (bit-packed) - not supported"
                % [s for s in shared if s != name]}
    try:
        raw = fc.encode_value(value, entry)
    except ValueError as e:
        return {"register": name, "error": str(e)}
    rd = fc.read_register(addr, cfg)
    return {"register": name, "address": addr, "type": entry.get("type"),
            "format": entry.get("format"),
            "current_value": (fc.decode_value(rd["raw"], entry) if rd["ok"] else None),
            "new_value": value, "raw": raw, "raw_hex": "0x%08X" % raw}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("assignments", nargs="+", help="NAME=VALUE [NAME=VALUE ...]")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    cfg = fc.load_config(); cat = fc.load_catalog(cfg)
    pairs = []
    for tok in a.assignments:
        if "=" not in tok:
            fc.emit(fc.tagged(fc.UNKNOWN, reason="expected NAME=VALUE, got '%s'" % tok)); return
        n, v = tok.split("=", 1)
        try:
            pairs.append((n.strip(), float(v)))
        except ValueError:
            fc.emit(fc.tagged(fc.UNKNOWN, reason="bad value in '%s'" % tok)); return
    plans = [build(n, v, cat, cfg) for n, v in pairs]
    errs = [p for p in plans if "error" in p]
    if errs:
        fc.emit(fc.tagged(fc.UNKNOWN, reason="one or more assignments invalid", plans=plans)); return
    if not a.apply:
        fc.emit(fc.tagged(fc.CONFIG, action="set_parameter", dry_run=True,
                          set=[{"register": p["register"], "current": p["current_value"],
                                "new": p["new_value"], "raw_hex": p["raw_hex"]} for p in plans],
                          note="DRY RUN - add --apply to write (each read-back verified)")); return
    results = []
    for p in plans:
        wr = fc.write_register(cfg, p["address"], p["raw"])
        if not wr["ok"]:
            results.append({"register": p["register"], "ok": False, "reason": wr["reason"]}); continue
        rb = fc.read_register(p["address"], cfg)
        got = (rb["raw"] & 0xFFFFFFFF) if rb["ok"] else None
        results.append({"register": p["register"], "requested": p["new_value"],
                        "raw_hex": p["raw_hex"],
                        "readback_value": (fc.decode_value(got, cat["meta"].get(p["register"], {}))
                                           if got is not None else None),
                        "verified": bool(got == p["raw"])})
    fc.emit(fc.tagged(fc.FACT, action="set_parameter", applied=results,
                      all_verified=all(r.get("verified") for r in results)))

if __name__ == "__main__":
    main()
