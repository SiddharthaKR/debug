#!/usr/bin/env python3
"""List the FPGA modules known to the register catalog. kind=config."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_common as fc

def main():
    cfg = fc.load_config()
    cat = fc.load_catalog(cfg)
    mods = {m: len(rs) for m, rs in sorted(cat["modules"].items())}
    gens = sorted((cfg.get("asg_channel_map") or {}).keys())
    fc.emit(fc.tagged(fc.CONFIG, modules=sorted(mods), register_counts=mods,
                      generators=gens, source=os.path.basename(cfg["catalog_path"]),
                      note="'modules' are register-catalog blocks; 'generators' (ASG0/ASG1) are "
                           "signal-generator OUTPUTS configured via configure_asg - not catalog "
                           "modules, and they have no registers here"))

if __name__ == "__main__":
    main()
