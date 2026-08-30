# Prompt to give MS Copilot (with dsp_tp.sv in context)

Paste this. Copilot has the RTL; it returns a topology.yaml my tool consumes.

---

You have access to my SystemVerilog file `dsp_tp.sv`, a Red Pitaya DSP datapath:
modules with I/O connected by wires, plus MUX/selector blocks whose selection is
controlled by memory-mapped registers (N-to-1, N-to-M, and N-to-N muxes).

Extract the datapath as a directed graph and output it as YAML with EXACTLY this
schema — output only the YAML, no prose:

nodes:
  <NAME>: {kind: source|process|sink, params_prefix: <REGISTER_PREFIX if process>}
fixed_edges:
  - [<SRC>, <DST>]          # only wires NOT chosen by any selector register
selectors:
  - dest: <NODE or OUTPUT being driven>
    register: <exact register name that holds this selection>
    field: "<bit range, only if one register selects multiple dests>"
    sources: { <int value>: <SOURCE NODE>, ... }   # from the RTL case/assign

RULES:
1. Nodes = engineer-visible DSP blocks (ADC0/1, ASG0/1, FGEN, BPF, SVF, MIX,
   LPF0/1/2, PI, GAIN0-3, DAC0/1, SPI_DAC0/1, SCOPE0/1, and each SEL/MUX).
   kind: source (ADC/ASG/FGEN), sink (DAC/SPI_DAC/SCOPE), else process.
   For process nodes set params_prefix to the prefix of that block's config
   registers in the register map (e.g. PI -> PI_*, GAIN0 -> GAIN0_*).
2. fixed_edges = every HARDWIRED wire, i.e. NOT selected by a register.
3. selectors = every MUX. Emit ONE entry PER driven destination (so an N-to-M or
   N-to-N mux becomes several entries). Give the exact `register` name (and
   `field` bits if one register drives several dests) and the integer
   value -> source-node map from the RTL.
4. Use the SAME register names as my register map / ntt_qctrl_seeting.json.
5. Do NOT invent nodes, edges, or registers. Only what is in dsp_tp.sv. If a
   selector value's source is unclear, map it to "UNKNOWN".
6. Exclude control/timing (clocks, resets, sample-and-hold strobes) - DATA PATH ONLY.
7. Every wire appears exactly once: either in fixed_edges OR as a selector source,
   never both.

Match the structure of the example file `topology.example.yaml` I will show you.
