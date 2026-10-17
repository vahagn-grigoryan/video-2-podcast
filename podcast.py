#!/usr/bin/env python3
"""Turn a video URL into a podcast episode and rebuild the show's feed.

    python podcast.py [--show vk|fireship] <url>
    python podcast.py [--show vk|fireship] --playlist <playlist or channel url>

Downloads the audio with yt-dlp, adds the episode to the show's episodes file
and regenerates its feed. With --playlist it adds the latest entries that are
not in the episodes file yet. Only the newest `keep` episodes are kept; the ids
of the rest are reported so their audio files can be deleted. Enclosure URLs
point at GitHub Release assets:
https://github.com/<REPO>/releases/download/ep-<id>/<id>.m4a
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
OUT = ROOT / "out"

REPO = os.environ.get("PODCAST_REPO", "vahagn-grigoryan/video-2-podcast")
SITE = os.environ.get("PODCAST_SITE", f"https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[-1]}/")
NOT_READY_HOURS = 3  # VK needs a while to process a new video; a failure younger than this is retried later

SHOWS = {
    "vk": {
        "title": os.environ.get("PODCAST_TITLE", "Самые Честные Новости"),
        "description": None,  # None: use the title
        "language": "ru",
        "episodes": "episodes.json",
        "feed": "feed.xml",
        "cover": "cover-2.jpg",  # rename the file and bump this to make podcast apps re-fetch new artwork
        "keep": int(os.environ.get("PODCAST_KEEP", "2")),  # newest episodes to keep; older ones are removed
        "format": "bestaudio[ext=m4a][abr<=70]/bestaudio[ext=m4a]",  # AAC audio-only (iOS-safe); ~70 kbps is plenty for speech
        "video_url": "https://vkvideo.ru/video{id}",
        "yt_dlp_args": [],
    },
    "fireship": {
        "title": "Fireship",
        "description": "High-intensity tech news, AI updates and coding tutorials from the Fireship YouTube channel.",
        "language": "en",
        "episodes": "fireship.json",
        "feed": "fireship.xml",
        "cover": "fireship-cover-2.jpg",
        "keep": 5,
        "format": "bestaudio[ext=m4a]",
        "video_url": "https://www.youtube.com/watch?v={id}",
        "yt_dlp_args": ["--js-runtimes", "node"],  # YouTube needs a JavaScript runtime
    },
}


def yt_dlp(show: dict, *args: str) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", *show["yt_dlp_args"], *args]


def download(show: dict, url: str) -> dict:
    OUT.mkdir(exist_ok=True)
    cmd = yt_dlp(
        show, "--no-playlist", "-f", show["format"],
        "--write-info-json", "-o", str(OUT / "%(id)s.%(ext)s"),
        "--print", "after_move:%(id)s",
        url,
    )
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


def age_hours(show: dict, url: str) -> float | None:
    """Hours since the video was published, or None if the site will not tell us."""
    cmd = yt_dlp(show, "--no-playlist", "--skip-download", "--print", "timestamp", url)
    try:
        out = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        return (datetime.now(timezone.utc).timestamp() - float(out)) / 3600
    except (subprocess.CalledProcessError, ValueError):
        return None


def new_playlist_urls(show: dict, playlist: str, latest: int, known: set[str]) -> list[str]:
    """URLs of the newest playlist entries we do not have yet, oldest first."""
    cmd = yt_dlp(show, "--flat-playlist", "--playlist-end", str(latest), "--print", "id", playlist)
    ids = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE).stdout.split()
    return [show["video_url"].format(id=i) for i in reversed(ids) if i not in known]


def write_feed(show: dict, episodes: list[dict]) -> None:
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
    title = show["title"]
    description = show["description"] or title
    (ROOT / show["feed"]).write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{escape(title)}</title>
    <link>{escape(SITE)}</link>
    <description>{escape(description)}</description>
    <language>{show['language']}</language>
    <itunes:image href="{escape(SITE)}{show['cover']}"/>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(items)}
  </channel>
</rss>
""")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?")
    parser.add_argument("--show", choices=SHOWS, default="vk")
    parser.add_argument("--playlist")
    parser.add_argument("--latest", type=int)
    args = parser.parse_args()
    if not args.url and not args.playlist:
        parser.error("give a video url or --playlist")
    show = SHOWS[args.show]
    keep = show["keep"]
    episodes_file = ROOT / show["episodes"]

    episodes = json.loads(episodes_file.read_text()) if episodes_file.exists() else []
    if args.url:
        urls = [args.url]
    else:
        urls = new_playlist_urls(show, args.playlist, args.latest or keep, {e["id"] for e in episodes})

    added = []
    for url in urls:
        try:
            episode = download(show, url)
        except subprocess.CalledProcessError:
            age = age_hours(show, url)
            if age is None or age >= NOT_READY_HOURS:
                raise
            print(f"Not ready yet ({age:.1f} h old, still being processed); will retry: {url}")
            continue
        episodes = [e for e in episodes if e["id"] != episode["id"]]
        episodes.append(episode)
        added.append(episode["id"])
        print(f"Added {episode['id']}: {episode['title']}")
    if not added:
        print("No new episodes")

    episodes.sort(key=lambda e: e["published"], reverse=True)
    removed = [e["id"] for e in episodes[keep:]]
    episodes = episodes[:keep]
    if removed:
        print(f"Removing old episodes: {' '.join(removed)}")
    episodes_file.write_text(json.dumps(episodes, ensure_ascii=False, indent=2) + "\n")
    write_feed(show, episodes)

    # Lets the caller (GitHub workflow or Mac job) upload new files and delete old ones.
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"ids={' '.join(added)}\n")
            f.write(f"removed={' '.join(removed)}\n")


if __name__ == "__main__":
    main()
