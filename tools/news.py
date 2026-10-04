"""Pick the one headline worth showing on the screen and write news.json.

Run hourly by .github/workflows/news.yml, which publishes the result to the
repo's `data` branch for the device to fetch. Claude is shown the current BBC
headlines and the story it picked last time, and replies with a single line
for the screen -- or NONE, which takes the news screen out of the rotation.

Usage: python tools/news.py <previous news.json> <output news.json>
"""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET

import anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
NEWS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
]
DEFAULT_INTERESTS = "major UK and world events, science, technology, London"


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
            "You curate a tiny news ticker on a 64x32 LED matrix in a home. "
            "You are shown current headlines once an hour. Pick the SINGLE "
            "story most worth the household knowing about, judged by "
            "significance and by their interests: " + interests + ". "
            "Rewrite it as one plain-text line, max 110 characters, no "
            "quotes, no markdown, understandable without context. "
            "If nothing is significant or everything is minor/repetitive, "
            "or the best story is essentially the same as the previous one, "
            "reply with exactly NONE."
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
            interests = json.load(f).get("news_interests") or DEFAULT_INTERESTS
    except (OSError, ValueError):
        interests = DEFAULT_INTERESTS

    headlines = fetch_headlines()
    if not headlines:
        sys.exit("no headlines fetched; leaving news.json as it is")

    last = prev.get("last_story", "")
    text = pick_story(headlines, interests, last)
    print("News:", repr(text))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"text": text, "last_story": text or last}, f)


if __name__ == "__main__":
    main()
