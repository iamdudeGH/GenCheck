"""Direct client for Google Stitch's official MCP endpoint.

Stitch MCP: https://stitch.googleapis.com/mcp  (JSON-RPC over streamable HTTP)
Auth: API key via the x-goog-api-key header (env STITCH_API_KEY).

Usage:
    set STITCH_API_KEY=AQ....
    python scripts/stitch_mcp.py list-tools
    python scripts/stitch_mcp.py call <tool> <json-args>
"""

import json
import os
import sys

import requests

URL = "https://stitch.googleapis.com/mcp"
KEY = os.environ.get("STITCH_API_KEY", "")
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "x-goog-api-key": KEY,
}


class StitchMCP:
    def __init__(self):
        self.session_id = None
        self.next_id = 1

    def _post(self, payload, expect_result=False):
        headers = dict(HEADERS)
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        r = requests.post(URL, headers=headers, json=payload, timeout=200)
        sid = r.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
        return self._parse(r)

    def _parse(self, r):
        ctype = r.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:
            # SSE: take the last data: line that parses as JSON
            for line in reversed(r.text.splitlines()):
                if line.startswith("data:"):
                    try:
                        return json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
            return None
        if not r.text.strip():
            return None
        return json.loads(r.text)

    def _msg(self, method, params=None):
        payload = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        self.next_id += 1
        if params is not None:
            payload["params"] = params
        return self._post(payload)

    def init(self):
        self._msg("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "gencheck", "version": "1.0"},
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def list_tools(self):
        return self._msg("tools/list").get("result", {})

    def call(self, tool, args):
        return self._msg("tools/call", {"name": tool, "arguments": args})


def main():
    if not KEY:
        sys.exit("set STITCH_API_KEY first")
    mcp = StitchMCP()
    mcp.init()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list-tools"

    if cmd == "list-tools":
        tools = mcp.list_tools().get("tools", [])
        for t in tools:
            print(f"\n== {t['name']}: {t.get('description', '')[:140]}")
            print(json.dumps(t.get("inputSchema", {}), indent=1)[:900])
    elif cmd == "call":
        tool, args = sys.argv[2], json.loads(sys.argv[3] if len(sys.argv) > 3 else "{}")
        out = mcp.call(tool, args)
        print(json.dumps(out, indent=1)[:6000])
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
