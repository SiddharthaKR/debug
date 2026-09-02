#!/usr/bin/env python3
"""Dev self-test for the MCP operations - exercises reads + the plan/commit loop
WITHOUT the MCP runtime and WITHOUT hardware (requires config mode=replay).
Backs up and restores the replay fixtures it writes. Run: python3 mcp_server/selftest.py"""
import os, sys, json, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_ops as ops
import fpga_common as fc

c = fc.load_config()
assert c["mode"] == "replay", "selftest must run in replay mode (set config mode=replay)"
FX = c["fixtures_dir"]
backups = {}
for f in ("mem.sample.json", "output_status.sample.json"):
    p = os.path.join(FX, f)
    if os.path.exists(p):
        backups[p] = p + ".selftest.bak"; shutil.copy2(p, backups[p])

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1; print("  PASS", name)
    else:
        failed += 1; print("  FAIL", name, "->", detail)

try:
    print("READS")
    check("get_status kind", ops.get_status().get("kind") in ("fact", "unknown"))
    m = ops.get_modules(); check("get_modules", m["kind"] == "config" and len(m["modules"]) > 0, m)
    gp = ops.get_parameter("PI0_SET_KP"); check("get_parameter PI0_SET_KP", gp["kind"] == "fact", gp)
    sp = ops.get_signal_path("DAC0"); check("get_signal_path DAC0", sp["kind"] in ("fact", "config"), sp)
    gr = ops.get_reachable("DAC0"); check("get_reachable DAC0", gr["kind"] == "config", gr)

    print("WRITE: plan -> commit (set_parameter)")
    pl = ops.plan_set_parameters({"PI0_SET_KP": 0.25})
    check("plan_set_parameters dry_run", pl.get("dry_run") is True and "plan_token" in pl, pl)
    tok = pl.get("plan_token")
    cm = ops.commit_write(tok)
    check("commit applied+verified", cm["kind"] == "fact" and cm.get("all_verified") is True, cm)
    check("token consumed", ops.commit_write(tok)["kind"] == "unknown")

    print("WRITE: drift abort")
    pl2 = ops.plan_set_parameters({"PI0_SET_KP": 0.9})
    # simulate an external change to the same register between plan and commit
    for w in ops._PLANS[pl2["plan_token"]]["writes"]:
        fc.write_register(c, w["address"], (w["planned_current_raw"] ^ 0x1) & 0xFFFFFFFF)
    ab = ops.commit_write(pl2["plan_token"])
    check("commit aborts on drift", ab.get("aborted") is True, ab)

    print("WRITE: plan -> commit (signal path)")
    pth = ops.plan_set_signal_path(["ASG1", "PI1", "LPF2"])
    if pth["kind"] == "unknown":
        print("  (skip path test - route not in this topology:", pth.get("reason"), ")")
    else:
        c2 = ops.commit_write(pth["plan_token"])
        check("commit signal path", c2["kind"] == "fact", c2)
finally:
    for orig, bak in backups.items():
        shutil.move(bak, orig)
    print("fixtures restored")

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
