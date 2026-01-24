import json
import logging
from datetime import datetime, timedelta, timezone

from yt_dlp import YoutubeDL

from .youtube_url import YTDLPLogger


def withinFuture(releaseTime=None, lookahead=24):
    if not releaseTime or not lookahead:
        return True
    release = datetime.fromtimestamp(releaseTime, timezone.utc)
    limit = datetime.now(timezone.utc) + timedelta(hours=lookahead)
    return release <= limit


def get_upcoming_or_live_videos(channel_id, tab=None, options=None, logger=None):
    if options is None:
        options = {}
    logger = logger or logging.getLogger()
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "sleep_interval": 1,
        "sleep_interval_requests": 1,
        "no_warnings": True,
        "cookiefile": options.get("cookies"),
        "playlist_items": "1-{}".format(options.get("playlist_items", 50)),
        "logger": YTDLPLogger(logger=logger),
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            if tab == "membership":
                if channel_id.startswith("UUMO"):
                    url = f"https://www.youtube.com/playlist?list={channel_id}"
                elif channel_id.startswith(("UC", "UU")):
                    url = "https://www.youtube.com/playlist?list={}".format("UUMO" + channel_id[2:])
                else:
                    ydl_opts.update({"playlist_items": "1:10"})
                    url = f"https://www.youtube.com/channel/{channel_id}/{tab}"

            elif tab == "streams":
                if channel_id.startswith("UU"):
                    url = f"https://www.youtube.com/playlist?list={channel_id}"
                elif channel_id.startswith("UC"):
                    url = "https://www.youtube.com/playlist?list={}".format("UU" + channel_id[2:])
                elif channel_id.startswith("UUMO"):
                    url = "https://www.youtube.com/playlist?list={}".format("UU" + channel_id[4:])
                else:
                    ydl_opts.update({"playlist_items": "1:10"})
                    url = f"https://www.youtube.com/channel/{channel_id}/{tab}"

            else:
                ydl_opts.update({"playlist_items": "1:10"})
                url = f"https://www.youtube.com/channel/{channel_id}/{tab}"

            info = ydl.extract_info(url, download=False)
            upcoming_or_live_videos = []
            for video in info["entries"]:
                if (
                    video.get("live_status") == "is_live"
                    or video.get("live_status") == "post_live"
                    or (
                        video.get("live_status") == "is_upcoming"
                        and withinFuture(
                            video.get("release_timestamp", None),
                            **({"lookahead": options["monitor_lookahead"]} if "monitor_lookahead" in options else {}),
                        )
                    )
                ):
                    logger.debug("({}) live_status = {}".format(video.get("id"), video.get("live_status")))
                    logger.debug(json.dumps(video))
                    upcoming_or_live_videos.append(video.get("id"))

            return list(set(upcoming_or_live_videos))
    except Exception:
        logger.exception("An unexpected error occurred when trying to fetch videos")
        raise
