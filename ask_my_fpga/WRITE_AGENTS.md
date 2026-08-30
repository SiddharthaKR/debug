# Ask My FPGA — WRITE / CONTROL mode

You can now CONFIGURE the FPGA, not just read it. You have the read tools (AGENTS.md)
PLUS write tools in `write_tools/`. Writes change LIVE hardware routing and outputs.

## Golden rule: dry-run -> show -> confirm -> apply
1. Every write tool defaults to a DRY RUN that prints exactly what it would change
   (each register: current -> new, decoded).
2. ALWAYS run the dry-run first and show the user the planned changes.
3. NEVER run a tool with `--apply` until the user has explicitly approved THIS change.
4. After `--apply`, report the read-back `verified: true/false` for every write.

## Feasibility first (read-only)
- `get_reachable.py TARGET`               - what sources can be routed to TARGET
- `get_reachable.py TARGET --source SRC`  - whether SRC is routable + the exact writes
Use this to confirm a path is possible BEFORE proposing writes. If a request isn't
directly possible (e.g. a scope can't tap PI0), get_reachable shows the workaround.

## Write tools (write_tools/)
- `set_signal_path.py SRC ... SINK [--apply]` - set the mux selectors for a path.
  Inverts the topology; writes only the muxes (fixed wiring is already there); each
  write is read-modify-write (only the bit-field changes) and read-back verified.
- `configure_asg.py ASG0|ASG1 --waveform --freq --amp --offset [--disable] [--apply]`
  - set a signal-generator output via the C# output API.
- `configure_scope.py SCOPE0|SCOPE1 [--source SIG] [--decimation N] [--start|--stop] [--apply]`
  - set what a scope taps (SCOPE_SEL register) and/or the acquisition sample rate.
- `set_parameter.py NAME VALUE [--apply]` - set a module register in engineering units
  (gains, coefficients, setpoints, offsets: PI0_SET_KP, GAIN0_GAIN, LPF0_ALPAH ...).

## Safety
- Writes reroute LIVE signals - a set_signal_path can break a running lock/experiment.
  The dry-run shows the current routing you would overwrite; surface it to the user.
- Only values present in the topology's selector tables are writable (range-checked).
- Distinguish FACT (read-back) / CONFIG (planned) / UNKNOWN as in read mode.

## Typical workflow (e.g. "send ASG1 through the chain to DAC0")
1. get_reachable.py DAC0 --source ASG1   -> confirm it's routable; get the mux writes.
   (If not routable, stop and tell the user - e.g. ASG0 is wired to no mux.)
2. set_signal_path.py ASG1 ... DAC0       -> dry-run, show, confirm, --apply (routing).
3. configure_asg.py ASG1 --waveform ...   -> dry-run, show, confirm, --apply (generation).
Steps 2 and 3 are independent; get_reachable gates step 2 (routing), not the ASG config.
To observe: configure_scope.py SCOPEx --source <an observable node>.
