"""Smoke test: boot chrome-devtools-mcp (headless, isolated) and list its tools.
Proves the MCP <-> Chrome bridge works. No DeepSeek key or login needed."""
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command="npx",
        args=["-y", "chrome-devtools-mcp@latest", "--headless", "--isolated",
              "--no-usage-statistics"],
    )
    print("Launching chrome-devtools-mcp (headless)...")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print(f"OK - {len(tools)} tools exposed:\n")
            for t in tools:
                print(f"  - {t.name}")
            print("\nAction test: open a page + snapshot...")
            await session.call_tool("navigate_page", {"url": "https://example.com"})
            res = await session.call_tool("take_snapshot", {})
            text = "".join(getattr(b, "text", "") for b in res.content)
            print("Snapshot:", len(text), "chars; contains 'Example':", "Example" in text)


if __name__ == "__main__":
    asyncio.run(main())
