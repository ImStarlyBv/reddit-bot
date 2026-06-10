"""
login_once.py — one-time manual login.

Opens Chrome via chrome-devtools-mcp using the SAME persistent profile dir that agent.py uses,
navigates to Reddit, and then just waits. You log into Google + Reddit by hand in that window.
When you close it, the session cookies stay in ./chrome-profile/ and every future agent run is
already authenticated. You only ever do this once (or again if the session expires).

Run:  python login_once.py
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

PROFILE_DIR = Path(os.getenv("CHROME_PROFILE_DIR", "./chrome-profile")).resolve()


def server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command="npx",
        args=[
            "-y",
            "chrome-devtools-mcp@latest",
            f"--userDataDir={PROFILE_DIR}",
            "--viewport", "1280x900",
            "--no-usage-statistics",
        ],
    )


async def main() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Persistent profile: {PROFILE_DIR}")
    print("Launching Chrome…")

    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("new_page", {"url": "https://www.reddit.com/login"})
            print(
                "\nChrome is open.\n"
                "  1. Log into Google (if Reddit uses 'Continue with Google').\n"
                "  2. Finish logging into Reddit so you see your avatar/feed.\n"
                "  3. Then come back here and press Enter to close.\n"
            )
            # Block on the operator, not the event loop.
            await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter when logged in… ")
            print("Saved. Your session now lives in the profile dir. You won't need to log in again.")


if __name__ == "__main__":
    asyncio.run(main())
