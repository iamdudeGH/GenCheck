"""End-to-end test of the GenCheck MCP server over stdio.

Spawns `python -m gencheck.mcp_server`, lists its tools, and calls the
read-only ones (cache checks + registry). gencheck_validate is not called
here — it costs real consensus fees and is the same code path the demo and
benchmarks already exercised live.

Usage:
    .venv-deploy/Scripts/python scripts/test_mcp.py
"""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gencheck.mcp_server"],
        cwd=None,
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])
            assert {t.name for t in tools.tools} == {
                "gencheck_check_domain", "gencheck_validate",
                "gencheck_official_domain"}, "unexpected tool set"

            for domain in ["www.amazon.com", "sephora.com",
                           "never-validated.example"]:
                res = await session.call_tool(
                    "gencheck_check_domain", {"domain": domain})
                payload = json.loads(res.content[0].text)
                print(f"check_domain({domain}):",
                      payload.get("status"), "->", payload.get("decision"))

            res = await session.call_tool(
                "gencheck_official_domain", {"brand": "amazon"})
            print("official_domain(amazon):", res.content[0].text)

            # validate without a key must fail closed with a clear error
            res = await session.call_tool(
                "gencheck_validate",
                {"checkout_url": "https://www.amazon.com/gp/cart/view.html",
                 "brand": "amazon"})
            payload = json.loads(res.content[0].text)
            print("validate (no key):", payload.get("status"),
                  "->", payload.get("decision"), "|",
                  payload.get("reason", "")[:60])
            assert payload["decision"] == "BLOCK"

    print("\nMCP server test: OK")


if __name__ == "__main__":
    asyncio.run(main())
