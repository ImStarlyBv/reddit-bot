"""Attach to the already-running debug Chrome (connect mode) and open a Google sign-in tab.
Proves connect mode works AND gives you a clean tab to log in."""
import asyncio, os
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
BROWSER_URL = os.getenv("BROWSER_URL", "http://127.0.0.1:9222")


async def main():
    params = StdioServerParameters(command="npx", args=[
        "-y", "chrome-devtools-mcp@latest", f"--browserUrl={BROWSER_URL}",
        "--no-usage-statistics"])
    print(f"Attaching to your Chrome at {BROWSER_URL} ...")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            pages_before = await session.call_tool("list_pages", {})
            print("Connected. Opening Google sign-in tab...")
            await session.call_tool("new_page", {"url": "https://accounts.google.com/signin"})
            print("Done. Switch to that Chrome window and log into Google by hand.")


if __name__ == "__main__":
    asyncio.run(main())
