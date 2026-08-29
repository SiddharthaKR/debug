#!/usr/bin/env python3
"""TEMPLATE — copy this to make a new read-only tool for a new C# endpoint.

Steps:
  1) Add the path to config.json under "endpoints", e.g.
        "endpoints": { ..., "my_thing": "/api/my/thing" }
  2) Copy this file to tools/get_my_thing.py and edit the 3 marked lines.
  3) (optional) drop a fixtures/my_thing.sample.json so it runs in replay mode.

Rules: READ ONLY. Never call a write/config endpoint. Always emit a kind tag:
  fc.FACT (live hw), fc.CONFIG (catalog metadata), fc.MEASUREMENT (from samples),
  fc.UNKNOWN (unresolved/failed).
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

ENDPOINT_KEY = "my_thing"          # <-- (1) must match a key in config.endpoints
NEEDS_DEVICE_ID = True             # <-- (2) True if the API needs ?deviceId=...
HTTP_METHOD = "GET"                # <-- (3) "GET" or "POST" (add body=... if POST)

def main():
    ap = argparse.ArgumentParser()
    # ap.add_argument("name")      # add args your endpoint needs
    ap.parse_args()
    cfg = fc.load_config()
    try:
        resp = fc.call_api(cfg, ENDPOINT_KEY, method=HTTP_METHOD, device=NEEDS_DEVICE_ID)
    except Exception as e:  # noqa
        fc.emit(fc.tagged(fc.UNKNOWN, endpoint=ENDPOINT_KEY, reason=str(e)))
        return
    fc.emit(fc.tagged(fc.FACT, endpoint=ENDPOINT_KEY, data=resp))

if __name__ == "__main__":
    main()
