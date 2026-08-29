#!/usr/bin/env python3
"""Live generator/output status for the active device. kind=fact.
Example of a GET endpoint that needs the deviceId query param."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

def main():
    cfg = fc.load_config()
    try:
        resp = fc.call_api(cfg, "output_status", device=True)   # GET /api/output/status?deviceId=...
    except Exception as e:  # noqa
        fc.emit(fc.tagged(fc.UNKNOWN, endpoint="output_status", reason=str(e)))
        return
    fc.emit(fc.tagged(fc.FACT, endpoint="output_status",
                      device=fc.resolve_device_id(cfg), data=resp))

if __name__ == "__main__":
    main()
