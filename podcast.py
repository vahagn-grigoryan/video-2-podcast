#!/usr/bin/env python3
"""Turn a video URL into a podcast episode and rebuild feed.xml.

    python podcast.py <url>

Downloads the audio with yt-dlp, adds the episode to
episodes.json and regenerates feed.xml. Enclosure URLs point at GitHub
Release assets: https://github.com/<REPO>/releases/download/ep-<id>/<id>.m4a
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent
EPISODES = ROOT / "episodes.json"
FEED = ROOT / "feed.xml"
OUT = ROOT / "out"

REPO = os.environ.get("PODCAST_REPO", "vahagn-grigoryan/video-2-podcast")
TITLE = os.environ.get("PODCAST_TITLE", "My VK Audio")
SITE = os.environ.get("PODCAST_SITE", f"https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[-1]}/")
KEEP = 100


def download(url: str) -> dict:
    OUT.mkdir(exist_ok=True)
    cmd = [
        sys.executable, "-m", "yt_dlp", "--no-playlist",
        "-f", "bestaudio[abr<=70]/bestaudio",  # VK offers AAC audio-only streams; ~70 kbps is plenty for speech
        "--write-info-json", "-o", str(OUT / "%(id)s.%(ext)s"),
        "--print", "after_move:%(id)s",
        url,
    ]
    video_id = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE).stdout.strip().splitlines()[-1]
    info = json.loads((OUT / f"{video_id}.info.json").read_text())
    audio = OUT / f"{video_id}.m4a"
    return {
        "id": video_id,
        "title": info.get("title") or "Untitled",
        "description": info.get("description") or "",
        "author": info.get("uploader") or "",
        "image": info.get("thumbnail") or "",
        "duration": int(info.get("duration") or 0),
        "published": datetime.fromtimestamp(info["timestamp"], timezone.utc).isoformat()
        if info.get("timestamp") else datetime.now(timezone.utc).isoformat(),
        "size": audio.stat().st_size,
        "url": f"https://github.com/{REPO}/releases/download/ep-{video_id}/{video_id}.m4a",
        "source": url,
    }


def write_feed(episodes: list[dict]) -> None:
    items = []
    for e in episodes[:KEEP]:
        pub = format_datetime(datetime.fromisoformat(e["published"]))
        items.append(f"""    <item>
      <title>{escape(e['title'])}</title>
      <description>{escape(e['description'])}</description>
      <pubDate>{pub}</pubDate>
      <guid isPermaLink="false">{escape(e['id'])}</guid>
      <link>{escape(e['source'])}</link>
      <enclosure url="{escape(e['url'])}" length="{e['size']}" type="audio/x-m4a"/>
      <itunes:duration>{e['duration']}</itunes:duration>
      <itunes:author>{escape(e['author'])}</itunes:author>
    </item>""")
    FEED.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{escape(TITLE)}</title>
    <link>{escape(SITE)}</link>
    <description>{escape(TITLE)}</description>
    <language>ru</language>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(items)}
  </channel>
</rss>
""")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    url = parser.parse_args().url

    episodes = json.loads(EPISODES.read_text()) if EPISODES.exists() else []
    episode = download(url)
    episodes = [e for e in episodes if e["id"] != episode["id"]]
    episodes.append(episode)
    episodes.sort(key=lambda e: e["published"], reverse=True)

    EPISODES.write_text(json.dumps(episodes, ensure_ascii=False, indent=2) + "\n")
    write_feed(episodes)

    # Lets the GitHub workflow pick up the id for the release tag.
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"id={episode['id']}\n")
    print(f"Added {episode['id']}: {episode['title']}")


if __name__ == "__main__":
    main()
