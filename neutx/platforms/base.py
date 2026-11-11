"""Common types for social platform adapters."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Callable

import httpx

from ..config import PlatformCredentials, Settings


class PlatformError(RuntimeError):
    """A failure talking to a platform. The message is shown to the user."""


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    refresh_expires_in: int | None = None
    scope: str = ""
    user_id: str | None = None  # some platforms return the account id with the token


@dataclass
class Profile:
    external_id: str
    username: str


@dataclass
class MediaFile:
    path: Path
    mime: str
    kind: str  # image | video
    size: int
    public_url: Callable[[], str] | None = None  # signed, time-limited URL (Instagram)


@dataclass
class PublishResult:
    external_id: str
    url: str | None


def check(resp: httpx.Response, what: str) -> dict:
    """Raise PlatformError with the platform's own error text for non-2xx responses."""
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400:
        detail = _error_text(body) or resp.text[:300]
        raise PlatformError(f"{what} failed ({resp.status_code}): {detail}")
    return body if isinstance(body, dict) else {}


def _error_text(body) -> str:
    if not isinstance(body, dict):
        return ""
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or err)[:300]
    if isinstance(err, str):
        return (err + (": " + body["error_description"] if body.get("error_description") else ""))[:300]
    if body.get("detail") or body.get("title"):
        return str(body.get("detail") or body.get("title"))[:300]
    if body.get("errors"):
        return str(body["errors"])[:300]
    return ""


async def read_chunks(path: Path, size: int) -> AsyncIterator[tuple[int, bytes]]:
    """Yield (offset, bytes) chunks without loading the whole file."""
    offset = 0
    with path.open("rb") as fh:
        while True:
            chunk = await asyncio.to_thread(fh.read, size)
            if not chunk:
                return
            yield offset, chunk
            offset += len(chunk)


class Platform(ABC):
    key: str = ""
    label: str = ""
    media_kinds: frozenset = frozenset({"video"})
    uses_pkce: bool = False
    caption_limit: int = 2200

    def __init__(self, creds: PlatformCredentials, settings: Settings, http: httpx.AsyncClient,
                 sleep: Callable[[float], "asyncio.Future"] = asyncio.sleep):
        self.creds, self.settings, self.http, self.sleep = creds, settings, http, sleep

    @property
    def configured(self) -> bool:
        return self.creds.configured

    @property
    def redirect_uri(self) -> str:
        return f"{self.settings.public_base_url}/api/oauth/{self.key}/callback"

    def info(self) -> dict:
        return {"key": self.key, "label": self.label, "configured": self.configured,
                "media_kinds": sorted(self.media_kinds)}

    @abstractmethod
    def authorize_url(self, state: str, code_challenge: str) -> str: ...

    @abstractmethod
    async def exchange_code(self, code: str, code_verifier: str) -> tuple[TokenSet, Profile]: ...

    @abstractmethod
    async def refresh(self, access_token: str, refresh_token: str | None) -> TokenSet: ...

    def needs_refresh(self, seconds_left: float | None, age_s: float) -> bool:
        return seconds_left is not None and seconds_left < 300

    @abstractmethod
    async def publish(self, access_token: str, account: dict, media: MediaFile,
                      title: str, caption: str) -> PublishResult: ...
