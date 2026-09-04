#!/usr/bin/env python3
"""Basic connectivity/status check against the C# server. kind=fact.
GET /api/status - the first thing to run to confirm the app is reachable."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

def main():
    cfg = fc.load_config()
    cfgfile = os.path.basename(fc._cfg_path())
    try:
        resp = fc.call_api(cfg, "status")     # GET /api/status
    except Exception as e:  # noqa
        fc.emit(fc.tagged(fc.UNKNOWN, endpoint="status", config_file=cfgfile,
                          device_id=cfg.get("device_id"), mode=cfg.get("mode"),
                          base_url=cfg.get("base_url"), reason=str(e)))
        return
    fc.emit(fc.tagged(fc.FACT, endpoint="status", config_file=cfgfile,
                      device_id=cfg.get("device_id"), mode=cfg.get("mode"),
                      base_url=cfg.get("base_url"), data=resp))

if __name__ == "__main__":
    main()
