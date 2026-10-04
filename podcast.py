#!/usr/bin/env python3
"""Turn a video URL into a podcast episode and rebuild feed.xml.

    python podcast.py <url>

    python podcast.py --playlist <playlist url>

Downloads the audio with yt-dlp, adds the episode to
episodes.json and regenerates feed.xml. With --playlist it adds the latest
entries that are not in episodes.json yet. Only the newest KEEP episodes are
kept; the ids of the rest are reported so their audio files can be deleted. Enclosure URLs point at GitHub
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
TITLE = os.environ.get("PODCAST_TITLE", "Самые Честные Новости")
SITE = os.environ.get("PODCAST_SITE", f"https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[-1]}/")
KEEP = int(os.environ.get("PODCAST_KEEP", "2"))  # newest episodes to keep; older ones are removed


def download(url: str) -> dict:
    OUT.mkdir(exist_ok=True)
    cmd = [
        sys.executable, "-m", "yt_dlp", "--no-playlist",
        "-f", "bestaudio[ext=m4a][abr<=70]/bestaudio[ext=m4a]",  # AAC audio-only (iOS-safe); ~70 kbps is plenty for speech
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


def new_playlist_urls(playlist: str, latest: int, known: set[str]) -> list[str]:
    """URLs of the newest playlist entries we do not have yet, oldest first."""
    cmd = [sys.executable, "-m", "yt_dlp", "--flat-playlist", "--playlist-end", str(latest), "--print", "id", playlist]
    ids = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE).stdout.split()
    return [f"https://vkvideo.ru/video{i}" for i in reversed(ids) if i not in known]


def write_feed(episodes: list[dict]) -> None:
    items = []
    for e in episodes:
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
    <itunes:image href="{escape(SITE)}cover.jpg"/>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(items)}
  </channel>
</rss>
""")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?")
    parser.add_argument("--playlist")
    parser.add_argument("--latest", type=int, default=KEEP)
    args = parser.parse_args()
    if not args.url and not args.playlist:
        parser.error("give a video url or --playlist")

    episodes = json.loads(EPISODES.read_text()) if EPISODES.exists() else []
    urls = [args.url] if args.url else new_playlist_urls(args.playlist, args.latest, {e["id"] for e in episodes})

    added = []
    for url in urls:
        episode = download(url)
        episodes = [e for e in episodes if e["id"] != episode["id"]]
        episodes.append(episode)
        added.append(episode["id"])
        print(f"Added {episode['id']}: {episode['title']}")
    if not added:
        print("No new episodes")

    episodes.sort(key=lambda e: e["published"], reverse=True)
    removed = [e["id"] for e in episodes[KEEP:]]
    episodes = episodes[:KEEP]
    if removed:
        print(f"Removing old episodes: {' '.join(removed)}")
    EPISODES.write_text(json.dumps(episodes, ensure_ascii=False, indent=2) + "\n")
    write_feed(episodes)

    # Lets the GitHub workflow upload new files and delete old ones.
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"ids={' '.join(added)}\n")
            f.write(f"removed={' '.join(removed)}\n")


if __name__ == "__main__":
    main()
