"""check_x_login.py — browser-only smoke test. No DeepSeek, no API key needed.

Attaches to the debug Chrome, opens x.com/home, and reports whether the profile is logged in.
Read-only: it navigates and snapshots, nothing else.

Run:  python check_x_login.py
"""
import asyncio, os, re, sys
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

load_dotenv()
BROWSER_URL = os.getenv("BROWSER_URL", "http://127.0.0.1:9222")


def text_of(result):
    return "\n".join(getattr(b, "text", "") or "" for b in (getattr(result, "content", []) or []))


async def main():
    params = StdioServerParameters(command="npx", args=[
        "-y", "chrome-devtools-mcp@latest", f"--browserUrl={BROWSER_URL}", "--no-usage-statistics"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            print(f"[mcp] connected, {len(tools)} tools")
            print(f"[mcp] type_text available: {'type_text' in tools}")

            await session.call_tool("new_page", {"url": "https://x.com/home"})
            await asyncio.sleep(5)
            snap = text_of(await session.call_tool("take_snapshot", {}))

            low = snap.lower()
            logged_out = any(k in low for k in ["sign in to x", "iniciar sesión", "create account",
                                                "crear cuenta", "log in"])
            logged_in = any(k in low for k in ["what is happening", "qué está pasando",
                                               "post your reply", "home timeline", "for you"])
            print(f"\n[result] logged-in markers : {logged_in}")
            print(f"[result] logged-out markers: {logged_out}")
            handles = sorted(set(re.findall(r"@[A-Za-z0-9_]{2,15}", snap)))[:12]
            print(f"[result] handles on page   : {', '.join(handles) if handles else '(none)'}")
            print(f"\n--- snapshot head ({len(snap)} chars) ---")
            print("\n".join(snap.splitlines()[:45]))


if __name__ == "__main__":
    asyncio.run(main())
