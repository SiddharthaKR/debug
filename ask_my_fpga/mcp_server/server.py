#!/usr/bin/env python3
"""Ask My FPGA - MCP server (local, stdio transport).

Exposes the existing engineering operations as MCP tools so ANY MCP-capable
client/harness (opencode, Claude Desktop, an IDE) can use them - not just via a
bash allowlist. All logic lives in fpga_ops.py (which imports fpga_common /
topology / the tool plan-builders); this file is only the MCP wiring.

Safety: reads are readOnly; writes are two-phase - plan_* (readOnly, returns a
diff + plan_token) then commit_write (destructive, re-verifies, then applies).
Secrets (x-device-token, deviceId) come from config.json via fpga_common and are
never tool parameters.

Run:  python3 mcp_server/server.py     (speaks MCP over stdio)
Config: uses config.json (or $FPGA_AGENT_CONFIG). Intended for live use.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpga_ops as ops

from mcp.server.fastmcp import FastMCP
try:
    from mcp.types import ToolAnnotations
    _RO = ToolAnnotations(title="read", readOnlyHint=True)
    _WR = ToolAnnotations(title="write", readOnlyHint=False, destructiveHint=True)
except Exception:  # older SDK without ToolAnnotations
    _RO = _WR = None

mcp = FastMCP("ask-my-fpga")

# reads + write-planning are read-only (they never change hardware)
for _fn in ops.READ_OPS + ops.PLAN_OPS:
    mcp.tool(annotations=_RO)(_fn)
# only commit_write changes hardware
mcp.tool(annotations=_WR)(ops.COMMIT_OP)

if __name__ == "__main__":
    mcp.run()
