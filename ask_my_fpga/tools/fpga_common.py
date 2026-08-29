"""Shared helpers for the Ask-My-FPGA read-only tools.

Provenance kinds emitted by every tool:
  fact        - value read live from hardware (via the C# memory/read API)
  config      - static metadata from the register catalog (setting.json)
  measurement - computed from acquired signal samples
  unknown     - could not be resolved/verified (never a silent wrong value)
"""
import json, os, struct, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACT, CONFIG, MEASUREMENT, UNKNOWN = "fact", "config", "measurement", "unknown"


# ---------- config ----------
def _cfg_path():
    return os.environ.get("FPGA_AGENT_CONFIG", os.path.join(ROOT, "config.json"))

def load_config():
    with open(_cfg_path()) as f:
        cfg = json.load(f)
    cfg.setdefault("base_url", "http://localhost:5000")
    cfg.setdefault("device_id", None)
    cfg.setdefault("adc_fullscale_v", 1.0)
    cfg.setdefault("adc_bits", 14)
    cfg.setdefault("packet_samples", 2048)
    cfg.setdefault("timeout", 5)
    cfg.setdefault("ws_path", "/ws/wave")
    cfg.setdefault("mode", "live")
    cfg["_root"] = ROOT
    cfg["fixtures_dir"] = _abs(cfg.get("fixtures_dir", "fixtures"))
    if cfg.get("catalog_path"):
        cfg["catalog_path"] = _abs(cfg["catalog_path"])
    return cfg

def _abs(p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(ROOT, p))

def _load_json(path):
    with open(path) as f:
        return json.load(f)


# ---------- register catalog ----------
_DUPS = []
def _dup_hook(pairs):
    seen = set()
    for k, _ in pairs:
        if k in seen:
            _DUPS.append(k)
        seen.add(k)
    return dict(pairs)

def _norm_addr(a):
    if isinstance(a, int):
        return "0x%08X" % a
    s = str(a).strip()
    return "0x%08X" % int(s, 16) if s.lower().startswith("0x") else "0x%08X" % int(s)

def load_catalog(cfg):
    """Load seeting.json. Detect the known duplicate-alias-key bug so
    those registers resolve to UNKNOWN instead of a silently-wrong address."""
    _DUPS.clear()
    cat = _load_json(cfg["catalog_path"])
    _reparse_for_dups(cfg["catalog_path"])
    aliases_raw = cat.get("aliases", {})
    aliases = {n: _norm_addr(a) for n, a in aliases_raw.items()}
    dup_names = set(_DUPS)
    addr_names = {}
    for n, a in aliases.items():
        addr_names.setdefault(a, []).append(n)
    overlaps = {a: ns for a, ns in addr_names.items() if len(ns) > 1}
    meta = {}
    modules = {}
    for e in cat.get("registers", []):
        name = e.get("address")  # entry.address holds the ALIAS name
        if not name:
            continue
        meta[name] = {"type": e.get("type", "uint32"),
                      "format": e.get("format"),
                      "default": e.get("value")}
        modules.setdefault(name.split("_")[0], []).append(name)
    # include alias-only names (muxes etc.) in their module bucket
    for n in aliases:
        modules.setdefault(n.split("_")[0], [])
        if n not in modules[n.split("_")[0]]:
            modules[n.split("_")[0]].append(n)
    return {"aliases": aliases, "dup_names": dup_names, "overlaps": overlaps,
            "meta": meta, "modules": modules,
            "endianness": cat.get("endianness", "little"),
            "version": cat.get("version")}

def _reparse_for_dups(path):
    _DUPS.clear()
    with open(path) as f:
        json.load(f, object_pairs_hook=_dup_hook)

def resolve_alias(name, cat):
    if name in cat["dup_names"]:
        return {"ok": False, "reason":
                "alias '%s' is defined multiple times in the catalog and the "
                "entries collapse (JSON last-wins) - address is ambiguous" % name}
    if name not in cat["aliases"]:
        return {"ok": False, "reason":
                "alias '%s' not found in catalog (may have been lost to a "
                "duplicate-key collapse)" % name}
    return {"ok": True, "address": cat["aliases"][name]}


# ---------- value decoding ----------
def _signed(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v & (1 << (bits - 1)) else v

def q_to_float(raw, fmt, bits=32):
    s = _signed(raw, bits)
    if fmt and fmt.upper().startswith("Q") and "." in fmt:
        frac = int(fmt.split(".")[1])
        return s / float(1 << frac)
    return s

def decode_value(raw, entry):
    t = (entry or {}).get("type", "uint32")
    fmt = (entry or {}).get("format")
    if t == "q":
        return q_to_float(raw, fmt)
    if t == "float":
        return struct.unpack("<f", struct.pack("<I", raw & 0xFFFFFFFF))[0]
    return raw & 0xFFFFFFFF


# ---------- HTTP to the C# API ----------
def _req(cfg, method, path, body=None):
    url = cfg["base_url"].rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=cfg.get("timeout", 5)) as r:
        txt = r.read().decode()
    return json.loads(txt) if txt else None

def http_get_json(cfg, path):
    return _req(cfg, "GET", path)

def http_post_json(cfg, path, body):
    return _req(cfg, "POST", path, body)

def resolve_device_id(cfg):
    if cfg.get("device_id"):
        return cfg["device_id"]
    if cfg["mode"] == "replay":
        st = _load_json(os.path.join(cfg["fixtures_dir"], "status.sample.json"))
        return st.get("activeDeviceId", "rp-1")
    st = http_get_json(cfg, "/api/status")
    return (st or {}).get("activeDeviceId") or "rp-1"

def _extract_value(resp):
    if resp is None:
        return None
    if isinstance(resp, (int, str)):
        try:
            return int(str(resp), 0)
        except ValueError:
            return None
    for k in ("value", "data", "result", "read", "word"):
        if isinstance(resp, dict) and k in resp and resp[k] is not None:
            try:
                return int(str(resp[k]), 0)
            except (ValueError, TypeError):
                return None
    return None

def read_register(address, cfg):
    """Return {'ok':True,'raw':int} or {'ok':False,'reason':str}."""
    if cfg["mode"] == "replay":
        mem = _load_json(os.path.join(cfg["fixtures_dir"], "mem.sample.json"))
        key = _norm_addr(address)
        alt = {k.lower(): v for k, v in mem.items()}
        val = mem.get(key, alt.get(key.lower()))
        if val is None:
            return {"ok": False, "reason": "address %s not in replay fixture" % key}
        return {"ok": True, "raw": int(str(val), 0)}
    try:
        dev = resolve_device_id(cfg)
        path = "/api/device/memory/read?deviceId=" + urllib.parse.quote(str(dev))
        resp = http_post_json(cfg, path, {"address": _norm_addr(address)})
        raw = _extract_value(resp)
        if raw is None:
            return {"ok": False, "reason": "could not parse read response: %r" % (resp,)}
        return {"ok": True, "raw": raw}
    except Exception as e:  # noqa
        return {"ok": False, "reason": "read failed: %s" % e}


# ---------- output ----------
def emit(obj):
    print(json.dumps(obj, indent=2, default=str))

def tagged(kind, **kw):
    kw["kind"] = kind
    return kw
