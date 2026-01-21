import argparse
import contextlib
import json
import logging

import yt_dlp

from .setup_logger import VERBOSE_LEVEL_NUM


class MyLogger:
    def __init__(self, logger: logging.Logger | logging.LoggerAdapter | None = None) -> None:
        self.logger = logger if logger is not None else logging.getLogger()

    def debug(self, msg: str) -> None:
        if not msg.startswith("[wait] Remaining time until next attempt:"):
            if msg.startswith("[debug] "):
                self.logger.debug(msg)
            else:
                self.info(msg)

    def info(self, msg: str) -> None:
        # Safe save to Verbose log level
        self.logger.log(VERBOSE_LEVEL_NUM, msg)

    def warning(self, msg: str) -> None:
        msg_str = str(msg)
        if (
            "private" in msg_str.lower()
            or "unavailable" in msg_str.lower()
            or "should already be available" in msg_str.lower()
        ):
            self.logger.info(msg_str)
            error_msg = "Private video. Sign in if you've been granted access to this video"
            raise yt_dlp.utils.DownloadError(error_msg)
        if "Video is no longer live. Giving up after" in msg_str:
            self.logger.info(msg_str)
            error_msg = "Video is no longer live"
            raise yt_dlp.utils.DownloadError(error_msg)
        if "this live event will begin in" in msg_str.lower() or "premieres in" in msg_str.lower():
            self.logger.info(msg)
        elif "not available on this app" in msg_str:
            self.logger.error(msg)
            raise yt_dlp.utils.DownloadError(msg_str)
        else:
            self.logger.warning(msg)

    def error(self, msg: str) -> None:
        self.logger.error(msg)


class VideoInaccessibleError(PermissionError):
    pass


class VideoProcessedError(ValueError):
    pass


class VideoUnavailableError(ValueError):
    pass


class VideoDownloadError(yt_dlp.utils.DownloadError):
    pass


class LivestreamError(TypeError):
    pass


def get_video_info(
    video_id: str,
    wait: bool | int | tuple[int, int | None] | str = True,
    cookies: str | None = None,
    additional_options: dict | None = None,
    proxy: dict | None = None,
    *,
    include_dash: bool = False,
    include_m3u8: bool = False,
    logger: logging.Logger | logging.LoggerAdapter | None = None,
    clean_info_dict: bool = False,
) -> tuple[dict, str | None]:
    url = str(video_id)

    if logger is None:
        logger = logging.getLogger()
    yt_dlp_logger = MyLogger(logger=logger)

    ydl_opts = {
        "retries": 25,
        "skip_download": True,
        "cookiefile": cookies,
        "writesubtitles": True,  # Extract subtitles (live chat)
        "subtitlesformat": "json",  # Set format to JSON
        "subtitleslangs": ["live_chat"],  # Only extract live chat subtitles
        "logger": yt_dlp_logger,
    }

    max_wait_tuple_len = 2
    if isinstance(wait, tuple):
        if not (0 < len(wait) <= max_wait_tuple_len):
            error_msg = "Wait tuple must contain 1 or 2 values"
            raise ValueError(error_msg)
        if len(wait) < max_wait_tuple_len:
            ydl_opts["wait_for_video"] = wait[0]
        else:
            ydl_opts["wait_for_video"] = (wait[0], wait[1])
    elif isinstance(wait, int):
        ydl_opts["wait_for_video"] = (wait, None)
    elif wait is True:
        ydl_opts["wait_for_video"] = (5, 300)
    elif isinstance(wait, str):
        ydl_opts["wait_for_video"] = parse_wait(wait)

    if additional_options:
        ydl_opts.update(additional_options)

    if proxy is not None:
        ydl_opts["proxy"] = next(iter(proxy.values()), None)

    ydl_opts.setdefault("extractor_args", {}).setdefault("youtube", {}).update({"formats": ["incomplete", "duplicate"]})
    if not include_dash:
        (ydl_opts.setdefault("extractor_args", {}).setdefault("youtube", {}).setdefault("skip", [])).append("dash")
    if not include_m3u8:
        (ydl_opts.setdefault("extractor_args", {}).setdefault("youtube", {}).setdefault("skip", [])).append("hls")

    info_dict = {}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info_dict = ydl.extract_info(url, download=False)
            info_dict = ydl.sanitize_info(info_dict=info_dict, remove_private_keys=clean_info_dict)

            for stream_format in info_dict.get("formats", []):
                with contextlib.suppress(Exception):
                    stream_format.pop("fragments", None)
            # Check if the video is private
            if not (info_dict.get("live_status") == "is_live" or info_dict.get("live_status") == "post_live"):
                error_msg = "Video has been processed, please use yt-dlp directly"
                raise VideoProcessedError(error_msg)
        except yt_dlp.utils.DownloadError as e:
            # If an error occurs, we can assume the video is private or unavailable
            error_str = str(e)
            if (
                "video is private" in error_str
                or "Private video. Sign in if you've been granted access to this video" in error_str
            ):
                error_msg = f"Video {video_id} is private, unable to get stream URLs"
                raise VideoInaccessibleError(error_msg) from e
            if "This live event will begin in" in error_str or "Premieres in" in error_str:
                error_msg = "Video is not yet available. Consider using waiting option"
                raise VideoUnavailableError(error_msg) from e
            if " members " in error_str or " members-only " in error_str:
                error_msg = f"Video {video_id} is a membership video. Requires valid cookies"
                raise VideoInaccessibleError(error_msg) from e
            if "not available on this app" in error_str:
                error_msg = f"Video {video_id} not available on this player"
                raise VideoInaccessibleError(error_msg) from e
            if "no longer live" in error_str.lower():
                error_msg = "Livestream has ended"
                raise LivestreamError(error_msg) from e
            raise

    if logger is None:
        logger = logging.getLogger(__name__)
    logger.debug("Info.json: %s", json.dumps(info_dict))
    return info_dict, info_dict.get("live_status")


def parse_wait(string: str) -> tuple[int, int | None]:
    try:
        if ":" in string:
            # Split by colon and convert both parts to integers
            parts = string.split(":")
            expected_parts = 2
            if len(parts) != expected_parts:
                error_msg = "Wait string must be in format 'min:max'"
                raise ValueError(error_msg)
            return (int(parts[0]), int(parts[1]))
        # Return a single-item tuple with None for max
        return (int(string), None)
    except ValueError as e:
        error_msg = f"'{string}' must be an integer or 'min:max'"
        raise argparse.ArgumentTypeError(error_msg) from e
