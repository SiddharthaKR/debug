#!/usr/bin/env python3
"""Registered device sessions + the active device. kind=fact.
Example of a GET endpoint that takes NO deviceId."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

def main():
    cfg = fc.load_config()
    try:
        resp = fc.call_api(cfg, "sessions")                     # GET /api/devices/sessions
    except Exception as e:  # noqa
        fc.emit(fc.tagged(fc.UNKNOWN, endpoint="sessions", reason=str(e)))
        return
    fc.emit(fc.tagged(fc.FACT, endpoint="sessions", data=resp))

if __name__ == "__main__":
    main()
