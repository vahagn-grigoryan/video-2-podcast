# Самые Честные Новости: VK playlist as a podcast

Turns a VK Video playlist into a podcast feed for Overcast (or any podcast app).
It runs entirely on GitHub, so no computer or server has to stay on.

**Feed URL:** `https://vahagn-grigoryan.github.io/video-2-podcast/feed.xml`
In Overcast: *Add URL* and paste it.

## How it works

1. A scheduled GitHub Actions run checks the VK playlist for new videos.
2. `yt-dlp` downloads the audio-only AAC stream (about 70 kbps, roughly 20 MB per episode).
3. The audio goes to a GitHub Release (`ep-<video id>`). The episode list goes to `episodes.json`, and `feed.xml` is rebuilt from it.
4. GitHub Pages serves `feed.xml` and the cover image. The podcast app downloads the audio from the Release.

## Schedule

The show publishes Fridays at about 05:45 UTC and Tuesday evenings (15:40 to 19:52 UTC).
The workflow checks at these times (UTC), set in `.github/workflows/add-episode.yml`:

- Fridays every 15 minutes, 05:07 to 08:52
- Tuesdays every 15 minutes, 15:07 to 22:52
- Every hour at :37, around the clock, as a catch-up

GitHub's scheduler is best effort. Measured over 59 hours (Oct 6 to 9, 2026), only 11 of 74 scheduled slots fired (15%), 4 to 7 hours apart.
Episodes therefore show up anywhere from minutes to a few hours after VK publishes them (observed: 47 minutes and 3 h 38 min).
A cron change does not fix this. The fix would be an outside timer (for example cron-job.org with a repo-limited access token) calling the workflow's "Run workflow" API every 10 minutes during the windows above. It is not set up.
A run with nothing new takes about 25 seconds and costs nothing on a public repo.
An episode that VK is still processing is skipped and retried on the next check. If it is still not ready after 3 hours, the run fails and GitHub emails you.

## Only the newest two episodes are kept

On every run, older episodes are dropped from the feed and their audio is deleted from GitHub.
Change the number with `PODCAST_KEEP` (default 2) in `podcast.py`.
The playlist check looks at the same number of newest videos, so a deleted episode does not come back.

## Add an episode by hand

GitHub repo → **Actions** → **Add episode** → **Run workflow**.
Paste a video URL, or leave the field empty to check the playlist now.

## Change things

| What | Where |
| --- | --- |
| Show name | `TITLE` in `podcast.py` (or the `PODCAST_TITLE` variable) |
| Playlist | `PLAYLIST` in `.github/workflows/add-episode.yml` |
| Cover art | Add a square image (1400×1400 or larger) under a new name, e.g. `cover-3.jpg`, and set `COVER` in `podcast.py` to it. A new name is needed because Overcast caches artwork by URL. |
| Audio quality | The `-f` format in `download()` in `podcast.py` |

Overcast caches artwork and the show name. After changing them, you may need to re-add the feed.

## If it stops working

- **No new episodes:** check the **Actions** tab for a failed run. GitHub emails you about failed scheduled runs if Actions notifications are on.
- **Failed run:** open it and read the `podcast.py` step. A VK error usually means VK changed something, and `pip install -U yt-dlp` (which every run does) often already fixes it.
- **Schedule paused:** GitHub pauses scheduled workflows after 60 days without repo activity. New episodes count as activity. If it happens anyway, re-enable the workflow on the Actions tab.

## Good to know

- The repo, the feed and the audio files are public. Anyone with the URL can download them.
- Downloads from VK are very slow from some home connections but fast from GitHub's servers. Test on GitHub, not on a laptop.
- Only VK has been tried. YouTube may block GitHub's servers.
