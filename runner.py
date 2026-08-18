"""
runner.py — the 24/7 outer loop.

Runs forever. Each cycle it calls agent.run_task() once (a bounded task), enforcing the standing
rules in code (instructions.md only *states* them — this file *holds* them):

  * 1 original Christian post per day   — tracked in engagement_state.json, resets at midnight.
  * 3 comments per day                  — on 3 DIFFERENT posts, tracked by permalink URL.
  * >= 5 minutes between any two writes — enforced by the spacing gate + the cycle sleep.

The runner decides the JOB for each cycle (post first, then comments) and hands the agent a random
search term so it doesn't crawl the same results every time.

The agent reports what it did by ending its answer with one machine line:
    RESULT: POSTED <url>       (it published its own post)
    RESULT: COMMENTED <url>    (it replied to that post)
    RESULT: NONE               (it only read / was gated)
The runner parses that to update the daily state.

Run:  python runner.py        (leave it running; Ctrl-C to stop)
Requires: the debug Chrome up on BROWSER_URL, logged into X, and ALLOW_WRITES=true in .env.
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
MAX_ORIGINAL_POSTS = int(os.getenv("MAX_ORIGINAL_POSTS_PER_DAY", "1"))
MAX_COMMENTS = int(os.getenv("MAX_COMMENTS_PER_DAY", "3"))
MIN_WRITE_GAP = int(os.getenv("MIN_WRITE_GAP_SECONDS", "300"))  # 5 minutes
BROWSER_URL = agent.BROWSER_URL

# Rotated so the agent sees different people each cycle instead of the same top results.
SEARCH_TERMS = [
    "bible verse", "Jesus", "faith in God", "prayer request", "God is good",
    "scripture", "trusting God", "grace of God", "Christian encouragement",
    "praise God", "walking with Christ", "God's promises",
]

POST_TASK = (
    "JOB THIS CYCLE: write ONE original Christian post on X (mission A in your instructions).\n"
    "Compose it yourself — encouraging, personal, under 280 characters. Go to "
    "https://x.com/compose/post, click the textbox, type_text your post, verify it landed in the box "
    "and that the Post button is enabled, then click Post and confirm with a snapshot.\n"
    "End your final answer with EXACTLY ONE line: 'RESULT: POSTED <url>' if you published it "
    "(use 'RESULT: POSTED unknown' if you posted but cannot read the URL), otherwise 'RESULT: NONE'."
)

COMMENT_TASK = (
    "JOB THIS CYCLE: find ONE Christian post by a real person and comment on it (mission B in your "
    "instructions).\n"
    "Search https://x.com/search?q={term}&f=live , read the results, and open ONE genuine post you "
    "can respond to meaningfully. Do NOT pick any post already listed as commented in your engagement "
    "state. Read what they actually said, then write a short warm reply that is clearly about THEIR "
    "post. Click the reply box, type_text, verify, click Reply, confirm with a snapshot.\n"
    "Comment on ONE post only this cycle.\n"
    "End your final answer with EXACTLY ONE line: 'RESULT: COMMENTED <permalink>' if you replied, "
    "otherwise 'RESULT: NONE'."
)

IDLE_TASK = (
    "JOB THIS CYCLE: read only. Your daily post and comments are already used up. Browse X's Christian "
    "conversations and report briefly what you saw. Do NOT write anything — do not type in any compose "
    "box, do not click Post or Reply.\n"
    "End your final answer with EXACTLY ONE line: 'RESULT: NONE'."
)


def load_state() -> dict:
    today = date.today().isoformat()
    if STATE_FILE.exists():
        st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if st.get("date") == today:
            st.setdefault("original_posts", [])
            st.setdefault("comments", [])
            st.setdefault("last_write_ts", 0.0)
            return st
    return {"date": today, "original_posts": [], "comments": [], "last_write_ts": 0.0}


def save_state(st: dict) -> None:
    STATE_FILE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def browser_up() -> bool:
    try:
        urllib.request.urlopen(f"{BROWSER_URL}/json/version", timeout=5)
        return True
    except Exception:
        return False


def parse_result(text: str) -> tuple[str, str] | None:
    """Return ('posted'|'commented', url) or ('none', '') — or None if no marker was found."""
    text = text or ""
    m = re.search(r"RESULT:\s*POSTED\s+(\S+)", text, re.IGNORECASE)
    if m:
        return "posted", m.group(1).strip().rstrip(".,)")
    m = re.search(r"RESULT:\s*COMMENTED\s+(\S+)", text, re.IGNORECASE)
    if m:
        return "commented", m.group(1).strip().rstrip(".,)")
    if re.search(r"RESULT:\s*NONE", text, re.IGNORECASE):
        return "none", ""
    return None


async def main() -> None:
    print("=" * 64)
    print(" X (Twitter) Christian agent — 24/7 runner")
    print(f"  master writes : {'ON' if MASTER_WRITES else 'OFF (read-only — set ALLOW_WRITES=true)'}")
    print(f"  daily cap     : {MAX_ORIGINAL_POSTS} original post(s) + {MAX_COMMENTS} comments")
    print(f"  write spacing : {MIN_WRITE_GAP}s between writes")
    print(f"  browser       : {BROWSER_URL}")
    print("=" * 64, flush=True)

    cycle = 0
    while True:
        cycle += 1
        st = load_state()
        posts_used = len(st["original_posts"])
        comments_used = len(st["comments"])
        secs_since = time.time() - st["last_write_ts"]
        interval_ok = secs_since >= MIN_WRITE_GAP
        engage_enabled = MASTER_WRITES and interval_ok

        # Job selection: the original post comes first, then the comments.
        if posts_used < MAX_ORIGINAL_POSTS:
            job, task = "ORIGINAL POST", POST_TASK
        elif comments_used < MAX_COMMENTS:
            term = random.choice(SEARCH_TERMS)
            job, task = f"COMMENT ({comments_used + 1}/{MAX_COMMENTS}, term='{term}')", \
                COMMENT_TASK.format(term=term.replace(" ", "%20"))
        else:
            job, task = "IDLE (day complete)", IDLE_TASK
            engage_enabled = False  # nothing left to spend today

        note = (
            f"ENGAGEMENT STATE: original posts today = {posts_used}/{MAX_ORIGINAL_POSTS}, "
            f"comments today = {comments_used}/{MAX_COMMENTS}. "
            f"Seconds since last write: {int(secs_since)} (need >= {MIN_WRITE_GAP}). "
            + (f"Already commented on: {st['comments']}. " if st["comments"] else "")
            + ("You MAY write this cycle." if engage_enabled
               else "You may NOT write this cycle (spacing, master switch, or daily cap) — read only.")
        )

        print(f"\n{'#' * 64}\n# cycle {cycle}  |  {time.strftime('%Y-%m-%d %H:%M:%S')}  |  "
              f"job {job}  |  posts {posts_used}/{MAX_ORIGINAL_POSTS}  "
              f"comments {comments_used}/{MAX_COMMENTS}  |  "
              f"since last write {int(secs_since)}s  |  writes {'ON' if engage_enabled else 'OFF'}"
              f"\n{'#' * 64}", flush=True)

        if not browser_up():
            print("⚠ Chrome not reachable on", BROWSER_URL,
                  "— start it (start_chrome.ps1) & log into X. Retrying in 60s.", flush=True)
            await asyncio.sleep(60)
            continue

        try:
            answer = await agent.run_task(task, allow_writes=engage_enabled, runtime_note=note)
        except Exception as e:
            print(f"‼ cycle error: {e!r} — recovering, retry in 90s.", flush=True)
            await asyncio.sleep(90)
            continue

        # Update daily state from the agent's RESULT marker.
        # SAFETY: if writes were enabled and the result is ambiguous (no clear marker — e.g. the task
        # hit MAX_STEPS right after posting and never emitted one), we COUNT it as an engagement.
        # Better to under-engage than to blow past the daily cap by losing a real write.
        parsed = parse_result(answer)
        if parsed and parsed[0] == "posted":
            st["last_write_ts"] = time.time()
            st["original_posts"].append(parsed[1])
            print(f"✓ original post published ({len(st['original_posts'])}/{MAX_ORIGINAL_POSTS}): "
                  f"{parsed[1]}", flush=True)
            save_state(st)
        elif parsed and parsed[0] == "commented":
            st["last_write_ts"] = time.time()
            if parsed[1] in st["comments"]:
                print(f"⚠ agent replied to an already-engaged post: {parsed[1]} "
                      f"— not counting it twice.", flush=True)
            else:
                st["comments"].append(parsed[1])
                print(f"✓ comment posted ({len(st['comments'])}/{MAX_COMMENTS}): {parsed[1]}",
                      flush=True)
            save_state(st)
        elif parsed and parsed[0] == "none":
            print("· no engagement this cycle.", flush=True)
        elif engage_enabled:  # ambiguous AND writes were on -> assume a write may have happened
            st["last_write_ts"] = time.time()
            stamp = f"unconfirmed-{time.strftime('%H%M%S')}"
            if job.startswith("ORIGINAL"):
                st["original_posts"].append(stamp)
            else:
                st["comments"].append(stamp)
            print(f"⚠ ambiguous result with writes ON — counting it against the cap to stay safe "
                  f"(posts {len(st['original_posts'])}/{MAX_ORIGINAL_POSTS}, "
                  f"comments {len(st['comments'])}/{MAX_COMMENTS}). Check X to confirm.", flush=True)
            save_state(st)
        else:  # writes were off this cycle -> nothing could have been written
            print("· no marker, but writes were OFF — nothing posted.", flush=True)

        # Pace the next cycle. >= 5 min naturally keeps writes spaced; idle longer once the day's done.
        if len(st["original_posts"]) >= MAX_ORIGINAL_POSTS and len(st["comments"]) >= MAX_COMMENTS:
            nap = random.randint(1800, 3600)   # 30–60 min: day complete, just lurk
        else:
            nap = random.randint(MIN_WRITE_GAP, MIN_WRITE_GAP + 180)  # 5–8 min
        print(f"\n💤 sleeping {nap}s before next cycle…", flush=True)
        await asyncio.sleep(nap)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped.")
