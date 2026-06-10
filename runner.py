"""
runner.py — the 24/7 outer loop.

Runs forever. Each cycle it calls agent.run_task() once (a bounded task), enforcing the standing
rules in code (instructions.md only *states* them — this file *holds* them):

  * 2 distinct posts per day        — tracked by URL in engagement_state.json, resets at midnight.
  * discuss freely within those 2   — replies to already-engaged posts don't count as new posts.
  * >= 5 minutes between any writes  — enforced by the spacing gate + the cycle sleep.

The agent reports what it did by ending its answer with one machine line:
    RESULT: ENGAGED <url>     (it posted on that question)
    RESULT: NONE              (it only read / was gated)
The runner parses that to update the daily state.

Run:  python runner.py        (leave it running; Ctrl-C to stop)
Requires: the debug Chrome up on BROWSER_URL, logged into Quora, and ALLOW_WRITES=true in .env.
"""
import asyncio
import json
import os
import random
import re
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
import urllib.request

import agent  # reuse run_task() + config

load_dotenv()

HERE = Path(__file__).parent
STATE_FILE = HERE / "engagement_state.json"
MASTER_WRITES = os.getenv("ALLOW_WRITES", "false").lower() == "true"
MAX_POSTS_PER_DAY = int(os.getenv("MAX_POSTS_PER_DAY", "2"))
MIN_WRITE_GAP = int(os.getenv("MIN_WRITE_GAP_SECONDS", "300"))  # 5 minutes
BROWSER_URL = agent.BROWSER_URL

STANDING_TASK = (
    "Per your instructions, work on anime discussions now. Browse/search Quora for a genuine anime "
    "question. If engagement is ENABLED and you have not yet used your 2 posts today, you may engage "
    "ONE new anime question with a thoughtful answer. If you have already engaged today's posts, you "
    "may continue those same discussions (replies) or simply read — do NOT open a 3rd post. "
    "End your final answer with EXACTLY ONE line: 'RESULT: ENGAGED <full-quora-url>' if you posted "
    "something, otherwise 'RESULT: NONE'."
)


def load_state() -> dict:
    today = date.today().isoformat()
    if STATE_FILE.exists():
        st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if st.get("date") == today:
            return st
    return {"date": today, "posts": [], "last_write_ts": 0.0}  # fresh day


def save_state(st: dict) -> None:
    STATE_FILE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def browser_up() -> bool:
    try:
        urllib.request.urlopen(f"{BROWSER_URL}/json/version", timeout=5)
        return True
    except Exception:
        return False


def parse_result(text: str) -> str | None:
    """Return the engaged URL, '' for NONE, or None if no marker found."""
    m = re.search(r"RESULT:\s*ENGAGED\s+(\S+)", text or "", re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(".,)")
    if re.search(r"RESULT:\s*NONE", text or "", re.IGNORECASE):
        return ""
    return None


async def main() -> None:
    print("=" * 64)
    print(" Quora anime agent — 24/7 runner")
    print(f"  master writes : {'ON' if MASTER_WRITES else 'OFF (read-only — set ALLOW_WRITES=true)'}")
    print(f"  daily cap     : {MAX_POSTS_PER_DAY} posts/day")
    print(f"  write spacing : {MIN_WRITE_GAP}s between posts")
    print(f"  browser       : {BROWSER_URL}")
    print("=" * 64, flush=True)

    cycle = 0
    while True:
        cycle += 1
        st = load_state()
        posts_used = len(st["posts"])
        secs_since = time.time() - st["last_write_ts"]
        interval_ok = secs_since >= MIN_WRITE_GAP
        new_post_ok = posts_used < MAX_POSTS_PER_DAY
        # Writing is enabled if the master switch is on AND the 5-min spacing has elapsed.
        # The "no 3rd post" rule is conveyed to the agent via the note (replies still allowed).
        engage_enabled = MASTER_WRITES and interval_ok

        note = (
            f"ENGAGEMENT STATE: posts used today = {posts_used}/{MAX_POSTS_PER_DAY}. "
            f"New posts allowed today: {'YES' if new_post_ok else 'NO — only continue existing posts'}. "
            f"Seconds since last post: {int(secs_since)} (need >= {MIN_WRITE_GAP}). "
            + (f"Today's engaged posts: {st['posts']}. " if st["posts"] else "")
            + ("You MAY post this cycle." if engage_enabled
               else "You may NOT post this cycle (spacing or master switch) — read only.")
        )

        print(f"\n{'#' * 64}\n# cycle {cycle}  |  {time.strftime('%Y-%m-%d %H:%M:%S')}  |  "
              f"posts {posts_used}/{MAX_POSTS_PER_DAY}  |  "
              f"since last post {int(secs_since)}s  |  writes {'ON' if engage_enabled else 'OFF'}"
              f"\n{'#' * 64}", flush=True)

        if not browser_up():
            print("⚠ Chrome not reachable on", BROWSER_URL,
                  "— start it (start_chrome.ps1) & log into Quora. Retrying in 60s.", flush=True)
            await asyncio.sleep(60)
            continue

        try:
            answer = await agent.run_task(STANDING_TASK, allow_writes=engage_enabled,
                                          runtime_note=note)
        except Exception as e:
            print(f"‼ cycle error: {e!r} — recovering, retry in 90s.", flush=True)
            await asyncio.sleep(90)
            continue

        # Update daily state from the agent's RESULT marker.
        # SAFETY: if writes were enabled and the result is ambiguous (no clear "NONE" — e.g. the task
        # hit MAX_STEPS right after posting and never emitted the marker), we COUNT it as an
        # engagement. Better to under-engage than to blow past the daily cap by losing a real post.
        url = parse_result(answer)
        if url:  # explicit "RESULT: ENGAGED <url>"
            st["last_write_ts"] = time.time()
            if url not in st["posts"] and len(st["posts"]) < MAX_POSTS_PER_DAY:
                st["posts"].append(url)
                print(f"✓ NEW post engaged ({len(st['posts'])}/{MAX_POSTS_PER_DAY}): {url}", flush=True)
            else:
                print(f"✓ continued discussion on existing post: {url}", flush=True)
            save_state(st)
        elif url == "":  # explicit "RESULT: NONE" — trustworthy no-op
            print("· no engagement this cycle.", flush=True)
        elif engage_enabled:  # ambiguous AND writes were on -> assume a post may have happened
            st["last_write_ts"] = time.time()
            st["posts"].append(f"unconfirmed-{time.strftime('%H%M%S')}")
            print(f"⚠ ambiguous result with writes ON — counting as an engagement to stay under the "
                  f"cap ({len(st['posts'])}/{MAX_POSTS_PER_DAY}). Check Quora to confirm.", flush=True)
            save_state(st)
        else:  # writes were off this cycle -> nothing could have been posted
            print("· no marker, but writes were OFF — nothing posted.", flush=True)

        # Pace the next cycle. >= 5 min naturally keeps writes spaced; idle longer when day is done.
        if len(st["posts"]) >= MAX_POSTS_PER_DAY:
            nap = random.randint(1200, 1800)   # 20–30 min: daily posts done, just lurk/continue
        else:
            nap = random.randint(MIN_WRITE_GAP, MIN_WRITE_GAP + 180)  # 5–8 min
        print(f"\n💤 sleeping {nap}s before next cycle…", flush=True)
        await asyncio.sleep(nap)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped.")
