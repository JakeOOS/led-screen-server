"""Decide whether anything in the news deserves the screen, and write news.json.

Run hourly by .github/workflows/news.yml, which publishes the result to the
repo's `data` branch for the device to fetch. Claude is shown the current BBC
headlines and the last story it put up, and replies with a single line for
the screen -- or, most hours, NONE. The news screen only exists while there
is a story: one that makes the cut stays up for "news_hours" (config.json),
then the screen drops out of the rotation until the next one.

Usage: python tools/news.py <previous news.json> <output news.json>
"""

import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

import anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
NEWS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
]
DEFAULT_INTERESTS = "major UK and world events, science, technology, London"
DEFAULT_HOURS = 6


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
            print("RSS error", url, e)
    return out


def pick_story(headlines, interests, last):
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=500,
        output_config={"effort": "low"},
        system=(
            "You decide whether a small 64x32 LED screen in a home should "
            "interrupt its usual train times and weather with a news story. "
            "You are shown current headlines once an hour. The screen is "
            "for the rare story the household would want to be told about "
            "the moment they walk past: a major event, a real turning "
            "point, or something that directly affects life in London. The "
            "household's interests are: " + interests + ". "
            "Ordinary news does not qualify, however prominent the "
            "headline: routine politics, ongoing stories with no decisive "
            "development, opinion, sport results, celebrity and "
            "human-interest pieces. On most hours nothing qualifies, and "
            "the right answer is exactly NONE. Also answer NONE if the "
            "best story is essentially the one previously shown, unless "
            "there has been a major new development in it. "
            "When a story does qualify, reply with it rewritten as one "
            "plain-text line, max 110 characters, no quotes, no markdown, "
            "understandable without context, and nothing else."
        ),
        messages=[{
            "role": "user",
            "content": ("Previously shown story: "
                        + (last or "(none)")
                        + "\n\nCurrent headlines:\n"
                        + "\n".join(headlines)),
        }],
    )
    text = ""
    if response.stop_reason != "refusal":
        text = next((b.text for b in response.content if b.type == "text"), "").strip()
    return "" if text.upper() == "NONE" else text[:160]


def main():
    prev_path, out_path = sys.argv[1], sys.argv[2]
    try:
        with open(prev_path) as f:
            prev = json.load(f)
    except (OSError, ValueError):
        prev = {}
    try:
        with open(os.path.join(HERE, "..", "config.json")) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    interests = cfg.get("news_interests") or DEFAULT_INTERESTS
    hold = float(cfg.get("news_hours") or DEFAULT_HOURS) * 3600

    headlines = fetch_headlines()
    if not headlines:
        sys.exit("no headlines fetched; leaving news.json as it is")

    last = prev.get("last_story", "")
    since = prev.get("since", 0)
    now = int(time.time())
    text = pick_story(headlines, interests, last)
    print("Claude:", repr(text or "NONE"))
    if text:
        out = {"text": text, "last_story": text, "since": now}
    elif prev.get("text") and now - since < hold:
        out = prev                       # nothing new; the current story stays up
    else:
        out = {"text": "", "last_story": last, "since": since}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
