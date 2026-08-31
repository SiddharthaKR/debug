#!/usr/bin/env python3
"""WRITE TOOL - configure or stop an ASG output.
  configure_asg.py ASG1 --waveform SINE --freq 1000 --amp 0.5        (dry run)
  configure_asg.py ASG1 --waveform SINE --freq 1000 --amp 0.5 --apply
  configure_asg.py ASG1 --stop --apply       # STOP the output (POST .../stop)
Dry-run by default; --apply performs it, then read-back via /api/output/status."""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import fpga_common as fc

def readback(cfg):
    try:
        return (fc._load_json(os.path.join(cfg["fixtures_dir"], "output_status.sample.json"))
                if cfg["mode"] == "replay" else fc.http_get_json(cfg, "/api/output/status"))
    except Exception as e:  # noqa
        return {"readback_error": str(e)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("asg", help="ASG0 or ASG1")
    ap.add_argument("--waveform", default="SINE")
    ap.add_argument("--freq", type=float, default=1000.0)
    ap.add_argument("--amp", type=float, default=1.0, help="Vpp")
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--stop", action="store_true", help="stop the output (dedicated stop endpoint)")
    ap.add_argument("--disable", action="store_true", help="configure with enabled=false")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    cfg = fc.load_config()
    ch = cfg.get("asg_channel_map", {"ASG0": 1, "ASG1": 2}).get(a.asg)
    if ch is None:
        fc.emit(fc.tagged(fc.UNKNOWN, asg=a.asg, reason="no channel mapping (config.asg_channel_map)")); return
    if a.stop:
        if not a.apply:
            fc.emit(fc.tagged(fc.CONFIG, action="stop_output", asg=a.asg, channel=ch,
                              dry_run=True, note="DRY RUN - add --apply to STOP this output")); return
        res = fc.output_stop(cfg, ch)
        if not res["ok"]:
            fc.emit(fc.tagged(fc.UNKNOWN, asg=a.asg, channel=ch, reason=res["reason"])); return
        fc.emit(fc.tagged(fc.FACT, action="stop_output", asg=a.asg, channel=ch, status=readback(cfg))); return
    body = {"waveform": a.waveform.upper(), "frequencyHz": a.freq, "amplitudeVpp": a.amp,
            "offsetV": a.offset, "enabled": (not a.disable)}
    if not a.apply:
        fc.emit(fc.tagged(fc.CONFIG, action="configure_asg", asg=a.asg, channel=ch,
                          planned=body, dry_run=True, note="DRY RUN - add --apply to write")); return
    res = fc.configure_output(cfg, ch, body)
    if not res["ok"]:
        fc.emit(fc.tagged(fc.UNKNOWN, asg=a.asg, channel=ch, reason=res["reason"])); return
    fc.emit(fc.tagged(fc.FACT, action="configure_asg", asg=a.asg, channel=ch, applied=body, status=readback(cfg)))

if __name__ == "__main__":
    main()
