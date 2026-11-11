from __future__ import annotations

import httpx

from ..config import Settings
from .base import MediaFile, Platform, PlatformError, Profile, PublishResult, TokenSet
from .instagram import Instagram
from .tiktok import TikTok
from .x import X
from .youtube import YouTube

__all__ = ["MediaFile", "Platform", "PlatformError", "Profile", "PublishResult", "TokenSet", "build_platforms"]


def build_platforms(settings: Settings, http: httpx.AsyncClient, **kw) -> dict[str, Platform]:
    return {
        "tiktok": TikTok(settings.tiktok, settings, http, **kw),
        "instagram": Instagram(settings.instagram, settings, http, **kw),
        "youtube": YouTube(settings.youtube, settings, http, **kw),
        "x": X(settings.x, settings, http, **kw),
    }
