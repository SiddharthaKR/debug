#!/usr/bin/env python3
"""Capture samples from the /ws/wave WebSocket stream (or a replay fixture) and
compute a scalar signal summary. kind=measurement.

Only the summary is returned - the raw sample array is never emitted, keeping it
out of the LLM context. Live capture needs: numpy, websocket-client.
Replay needs: numpy only.
"""
import argparse, json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

FS_BASE = 125_000_000  # Red Pitaya base sample rate (Hz), divided by decimation
HDR = struct.Struct("<IIHHI")  # magic, seq, channel, decimation, reserved
MAGIC = 0xDEADBEEF


def decode_packet(buf, packet_samples):
    if len(buf) < HDR.size:
        return None
    magic, seq, channel, dec, _ = HDR.unpack_from(buf, 0)
    if magic != MAGIC:
        return None
    data = struct.unpack_from("<%dh" % packet_samples, buf, HDR.size)
    return {"seq": seq, "channel": channel, "decimation": dec, "data": list(data)}


def capture_ws(cfg, channel, nsamples):
    import websocket  # websocket-client
    dev = fc.resolve_device_id(cfg)
    url = (cfg["base_url"].replace("http", "ws", 1).rstrip("/")
           + cfg["ws_path"] + "?deviceId=" + str(dev))
    ws = websocket.create_connection(url, timeout=cfg.get("timeout", 5))
    counts, dec = [], 1
    try:
        while len(counts) < nsamples:
            frame = ws.recv()
            if isinstance(frame, str):
                continue
            pkt = decode_packet(frame, cfg["packet_samples"])
            if not pkt or (channel is not None and pkt["channel"] != channel):
                continue
            dec = pkt["decimation"] or 1
            counts.extend(pkt["data"])
    finally:
        ws.close()
    return counts[:nsamples], dec


def load_replay(cfg, channel):
    wav = fc._load_json(os.path.join(cfg["fixtures_dir"], "wave.sample.json"))
    if isinstance(wav, dict):
        return wav["samples"], int(wav.get("decimation", 1))
    return wav, 1


def analyze(counts, dec, cfg):
    import numpy as np
    bits = cfg["adc_bits"]
    fs = FS_BASE / (dec or 1)
    x = np.asarray(counts, dtype=np.float64)
    n = x.size
    full = float(1 << (bits - 1))            # e.g. 8192 for 14-bit
    volts = x / full * cfg["adc_fullscale_v"]
    clip_count = int((np.abs(x) >= (full - 1)).sum())
    win = volts - volts.mean()
    spec = np.abs(np.fft.rfft(win * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    dom_i = int(spec[1:].argmax()) + 1 if n > 1 else 0
    order = np.argsort(spec[1:])[::-1][:5] + 1
    peaks = [{"frequency_hz": round(float(freqs[i]), 2),
              "magnitude": round(float(spec[i]), 4)} for i in order]
    return fc.tagged(
        fc.MEASUREMENT,
        sample_rate=fs, samples=n, decimation=dec,
        adc_fullscale_v=cfg["adc_fullscale_v"], adc_bits=bits,
        mean_v=round(float(volts.mean()), 6),
        rms_v=round(float(np.sqrt(np.mean(volts ** 2))), 6),
        peak_v=round(float(np.max(np.abs(volts))), 6),
        min_v=round(float(volts.min()), 6),
        max_v=round(float(volts.max()), 6),
        dominant_frequency_hz=round(float(freqs[dom_i]), 2),
        top_peaks=peaks,
        clipping=bool(clip_count > 0), clipped_samples=clip_count)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("signal", nargs="?", default="scope", help="label, e.g. DAC0")
    ap.add_argument("--channel", type=int, default=None)
    ap.add_argument("--nsamples", type=int, default=16384)
    a = ap.parse_args()
    cfg = fc.load_config()
    try:
        if cfg["mode"] == "replay":
            counts, dec = load_replay(cfg, a.channel)
        else:
            counts, dec = capture_ws(cfg, a.channel, a.nsamples)
    except Exception as e:  # noqa
        fc.emit(fc.tagged(fc.UNKNOWN, signal=a.signal,
                          reason="capture failed: %s" % e))
        return
    out = analyze(counts, dec, cfg)
    out["signal"] = a.signal
    fc.emit(out)


if __name__ == "__main__":
    main()
