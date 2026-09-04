# Ask My FPGA — Question Cookbook

> 🌐 Language: **English** · [日本語 / Japanese](QUESTIONS.ja.md)
>
> Every kind of question you can ask the agent about the FPGA, how to phrase it, the
> tool it triggers, and what you get back. Ask in plain English or Japanese — you
> never name a tool yourself; the agent picks it.

## How to phrase, in general
- **Use semantic names**, not addresses: `PI0_SET_KP`, `GAIN0_GAIN`, `DAC0`, `SCOPE0`.
- **One target at a time** for routing questions (ask about `DAC0`, then `SCOPE0`).
- **Every answer is tagged** `fact` (live read), `config` (from the catalog / fixed
  wiring), `measurement` (from captured samples), or `unknown`. Trust fact/measurement
  as observed; anything labelled interpretation is reasoning, not a reading.
- **Generators (ASG0/ASG1) are outputs**, not registers — ask "generate on ASG1",
  not "read the ASG1 register".
- **Writes are gated**: the agent shows a dry-run/plan first; you approve, then it
  applies and read-back-verifies. Say "apply" / "go ahead" to confirm.

---

## 1. Is it working? (environment & connectivity)
| Ask (any phrasing) | Tool | You get |
|---|---|---|
| "Run a status check." / "Is the server reachable?" / "Are we live or replay?" / "Which config / device am I on?" | `get_status` | server status + `config_file`, `device_id`, `mode` |
| "What devices are registered?" / "Which board is active?" | `get_sessions` | device sessions + active device |
| "Is any output/generator running now?" | `get_output_status` | live generator/output status |

## 2. What exists? (discovery)
| Ask | Tool | You get |
|---|---|---|
| "What modules are on the FPGA?" / "List the DSP blocks." | `get_modules` | catalog modules **+ generators** (ASG0/ASG1) |
| "What registers belong to the PI module?" | `get_modules` → `get_register_info` | module's register names, then details |
| "Tell me about PI0_SET_KP." / "What type/format/address is GAIN0_GAIN?" | `get_register_info NAME` | type (Q15.16 / float / uint32), format, default, address, any aliases sharing the address |

## 3. What is the current value? (reading state)
| Ask | Tool | You get |
|---|---|---|
| "What is PI0_SET_KP right now?" / "Read GAIN0_GAIN." / "Current value of LPF0_ALPAH?" | `get_parameter NAME` | decoded engineering value + raw hex + address (kind=fact) |
| "Show the live state of the PI and MIX modules." / "Dump all GAIN coefficients." | `get_fpga_state [--modules PI,MIX]` | per-module decoded snapshot of live values |

## 4. How is it wired? (routing & influence)
This is the heart of "any detail about the FPGA."
| Ask | Tool | You get |
|---|---|---|
| "What is the signal path to DAC0?" / "How does the signal reach SCOPE0?" / "Trace DAC0 upstream." | `get_signal_path TARGET` | the live path: fixed hops = config, mux selectors = fact, plus each mux's `alternatives` |
| "What modules affect DAC0?" / "What is currently feeding DAC0?" | `get_signal_path TARGET` | the `upstream_nodes` (current influencers) — **not** `get_modules` |
| "Which parameters/registers affect DAC0?" / "What settings influence the DAC0 signal?" | `get_affecting_parameters TARGET` | config registers of every module on the upstream path |
| "What can I route to DAC0?" / "Which sources can feed SCOPE0?" | `get_reachable TARGET` | all sources routable to the target + the direct mux options |
| "Can I route ASG1 to DAC0, and how?" / "Is PI0 reachable to SCOPE0?" | `get_reachable TARGET --source SRC` | routable yes/no + the exact selector writes to do it |

## 5. What does the signal actually look like? (measurement)
| Ask | Tool | You get |
|---|---|---|
| "Capture DAC0 and give me RMS and dominant frequency." / "Is there clipping on channel 1?" / "What's the DC offset?" | `capture_analyze_signal` | scalar summary: RMS, mean/DC, peak, min, max, dominant frequency, top FFT peaks, clipping (kind=measurement) |
| "Why does DAC0 / SCOPE0 look noisy?" | `get_signal_path` + module state + `capture_analyze_signal` | observations first (facts + measurements), then possible causes as interpretation with uncertainty — never a guessed cause asserted as fact |

## 6. Change something (writes — dry-run → approve → apply)
| Ask | Tool | Flow |
|---|---|---|
| "Set PI0_SET_KP to 0.5." / "Change GAIN0_GAIN to 1.5." / "Set BPF b0=0.1 b1=0.2 …" | `set_parameter` | dry-run diff → you approve → apply + read-back verify |
| "Generate a 1 kHz sine, 0.2 V on ASG1." / "Stop ASG1." | `configure_asg` | dry-run → approve → apply |
| "Route ASG1 through the chain to DAC0." | `get_reachable` → `set_signal_path` | check feasibility, then set the muxes (dry-run → approve → apply) |
| "Show DAC0 on SCOPE0, decimation 64, start acquisition." | `configure_scope` | dry-run → approve → apply |

## 7. Diagnostic workflows (chaining questions)
- **"Why is the output noisy?"** → ask for the signal path (`get_signal_path`), then the
  live module state (`get_fpga_state`), then a capture (`capture_analyze_signal`). The
  agent reports what it observed, then lists *possible* causes as interpretation.
- **"Did my change take effect?"** → after an apply, the agent already read-back-verifies;
  you can also ask `get_parameter NAME` again to confirm the live value.
- **"What would change if I reroute DAC0 to LPF2?"** → `get_reachable DAC0 --source LPF2`
  shows the exact selector writes before you commit anything.

## 8. Things the agent will refuse or flag
- Reading an ASG as if it were a register (it's an output → use `configure_asg`).
- A register whose address is shared/bit-packed for a whole-word write (`set_parameter`
  refuses it).
- Anything it cannot resolve in the catalog/topology → returned as `unknown`, stated
  plainly rather than guessed.
