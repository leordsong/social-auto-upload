"""Backward-compatible TikTok uploader import.

TikTok Studio now uses the maintained Chromium implementation.  Keeping this
module as a re-export prevents older integrations from running the stale
Firefox selector set.
"""

from uploader.tk_uploader.main_chrome import (
    TiktokVideo,
    cookie_auth,
    get_tiktok_cookie,
    tiktok_setup,
)

__all__ = ["TiktokVideo", "cookie_auth", "get_tiktok_cookie", "tiktok_setup"]
