"""The news screen's two chores, run by a scheduled Claude routine.

A scheduled Claude session decides whether anything in the news deserves the
screen; this script does everything around that decision:

    python3 tools/news.py brief            # print the rules, the last story
                                           # shown and the current headlines
    python3 tools/news.py publish "TEXT"   # put a story on the screen
    python3 tools/news.py publish NONE     # nothing qualifies this hour

`publish` keeps news.json on the repo's `data` branch, which is where the
screen fetches it. The news screen only exists while there is a story: one
that makes the cut stays up for "news_hours" (config.json), then the screen
drops out of the rotation until the next one. The branch is a single commit
that gets replaced, so main's history stays clean.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
NEWS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
]
DEFAULT_INTERESTS = "major UK and world events, science, technology, London"
DEFAULT_HOURS = 6

RULES = """\
You decide whether a small 64x32 LED screen in a home should interrupt its
usual train times and weather with a news story. The screen is for the rare
story the household would want to be told about the moment they walk past: a
major event, a real turning point, or something that directly affects life in
London. The household's interests are: {interests}.

Ordinary news does not qualify, however prominent the headline: routine
politics, ongoing stories with no decisive development, opinion, sport
results, celebrity and human-interest pieces. On most hours nothing
qualifies, and the right answer is NONE. Also answer NONE if the best story is
essentially the one previously shown, unless there has been a major new
development in it.

When a story does qualify, rewrite it as one plain-text line, max 110
characters, no quotes, no markdown, understandable without context."""


def git(*args, stdin=None):
    return subprocess.run(["git", *args], cwd=HERE, input=stdin, text=True,
                          capture_output=True)


def load_config():
    try:
        with open(os.path.join(HERE, "..", "config.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_previous():
    """news.json as it currently stands on the data branch ({} if none)."""
    if git("fetch", "-q", "origin", "data").returncode != 0:
        return {}
    try:
        return json.loads(git("show", "FETCH_HEAD:news.json").stdout)
    except ValueError:
        return {}


def fetch_headlines():
    out = []
    for url in NEWS_FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                root = ET.fromstring(r.read())
            for item in list(root.iter("item"))[:15]:
                title = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                if title:
                    out.append(f"- {title}" + (f" — {desc[:150]}" if desc else ""))
        except Exception as e:
            print("RSS error", url, e, file=sys.stderr)
    return out


def next_state(prev, text, now, hold):
    """What news.json should say given this hour's decision ('' = NONE)."""
    last = prev.get("last_story", "")
    since = prev.get("since", 0)
    if text:
        return {"text": text[:160], "last_story": text[:160], "since": now}
    if prev.get("text") and now - since < hold:
        return prev                      # nothing new; the current story stays up
    return {"text": "", "last_story": last, "since": since}


def brief():
    headlines = fetch_headlines()
    if not headlines:
        sys.exit("no headlines fetched")
    prev = load_previous()
    print(RULES.format(interests=load_config().get("news_interests") or DEFAULT_INTERESTS))
    print("\nPreviously shown story:", prev.get("last_story") or "(none)")
    print("\nCurrent headlines:\n" + "\n".join(headlines))


def publish(text):
    text = " ".join(text.split())
    if text.upper() == "NONE":
        text = ""
    prev = load_previous()
    hold = float(load_config().get("news_hours") or DEFAULT_HOURS) * 3600
    out = next_state(prev, text, int(time.time()), hold)
    if out == prev:
        print("unchanged:", repr(out.get("text", "")))
        return
    blob = git("hash-object", "-w", "--stdin", stdin=json.dumps(out)).stdout.strip()
    tree = git("mktree", stdin=f"100644 blob {blob}\tnews.json\n").stdout.strip()
    ident = ["-c", "user.name=voxel-news", "-c", "user.email=voxel-news@users.noreply.github.com"]
    commit = git(*ident, "commit-tree", tree, "-m", "news").stdout.strip()
    if not commit:
        sys.exit("could not build the news commit")
    push = git("push", "-f", "origin", f"{commit}:refs/heads/data")
    if push.returncode != 0:
        sys.exit("push to data branch failed: " + push.stderr.strip())
    print("published:", repr(out["text"]))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "brief":
        brief()
    elif len(sys.argv) == 3 and sys.argv[1] == "publish":
        publish(sys.argv[2])
    else:
        sys.exit(__doc__)
