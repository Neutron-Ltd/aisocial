"""TikTok: Login Kit (OAuth v2) + Content Posting API, Direct Post with FILE_UPLOAD.

Unaudited TikTok apps can only post privately (SELF_ONLY). Set
TIKTOK_PRIVACY_LEVEL once your app has passed TikTok's audit.
"""

from __future__ import annotations

import time
from urllib.parse import urlencode

from .base import MediaFile, Platform, PlatformError, Profile, PublishResult, TokenSet, check, read_chunks

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
API = "https://open.tiktokapis.com/v2"
MIN_CHUNK = 5 * 1024 * 1024
CHUNK = 10 * 1024 * 1024
JSON_HEADERS = {"Content-Type": "application/json; charset=UTF-8"}


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) per TikTok's media transfer rules."""
    if size <= 0:
        raise PlatformError("video file is empty")
    if size < MIN_CHUNK or size <= CHUNK:
        return size, 1
    return CHUNK, size // CHUNK  # trailing bytes ride on the last chunk (< 2x CHUNK)


class TikTok(Platform):
    key, label = "tiktok", "TikTok"
    caption_limit = 2200

    def authorize_url(self, state: str, code_challenge: str) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_key": self.creds.client_id,
            "scope": "user.info.basic,video.publish",
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": state,
        })

    async def _token(self, data: dict) -> TokenSet:
        body = check(await self.http.post(TOKEN_URL, data={
            "client_key": self.creds.client_id, "client_secret": self.creds.client_secret, **data,
        }), "TikTok token request")
        if "access_token" not in body:
            raise PlatformError(f"TikTok token request failed: {body.get('error_description') or body.get('error')}")
        return TokenSet(body["access_token"], body.get("refresh_token"), body.get("expires_in"),
                        body.get("refresh_expires_in"), body.get("scope", ""), body.get("open_id"))

    async def exchange_code(self, code: str, code_verifier: str) -> tuple[TokenSet, Profile]:
        tokens = await self._token({"code": code, "grant_type": "authorization_code", "redirect_uri": self.redirect_uri})
        if "video.publish" not in tokens.scope.split(","):
            raise PlatformError("TikTok did not grant the video.publish permission")
        if not tokens.user_id:
            raise PlatformError("TikTok token response did not include an open_id")
        creator = await self._creator_info(tokens.access_token)
        return tokens, Profile(external_id=tokens.user_id, username=creator.get("creator_username", ""))

    async def refresh(self, access_token: str, refresh_token: str | None) -> TokenSet:
        if not refresh_token:
            raise PlatformError("TikTok connection has no refresh token; reconnect the account")
        return await self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    async def _creator_info(self, token: str) -> dict:
        body = check(await self.http.post(f"{API}/post/publish/creator_info/query/",
                                          headers={**JSON_HEADERS, "Authorization": f"Bearer {token}"}),
                     "TikTok creator info")
        _raise_api_error(body, "TikTok creator info")
        return body.get("data") or {}

    async def publish(self, access_token: str, account: dict, media: MediaFile, title: str, caption: str) -> PublishResult:
        if media.kind != "video":
            raise PlatformError("TikTok accepts videos only")
        auth = {"Authorization": f"Bearer {access_token}"}
        creator = await self._creator_info(access_token)
        options = creator.get("privacy_level_options") or ["SELF_ONLY"]
        privacy = self.settings.tiktok_privacy_level if self.settings.tiktok_privacy_level in options else "SELF_ONLY"
        chunk_size, total = chunk_plan(media.size)
        init = check(await self.http.post(f"{API}/post/publish/video/init/", headers={**JSON_HEADERS, **auth}, json={
            "post_info": {
                "title": caption[: self.caption_limit],
                "privacy_level": privacy,
                "disable_comment": bool(creator.get("comment_disabled")),
                "disable_duet": bool(creator.get("duet_disabled")),
                "disable_stitch": bool(creator.get("stitch_disabled")),
                "is_aigc": True,
            },
            "source_info": {"source": "FILE_UPLOAD", "video_size": media.size,
                            "chunk_size": chunk_size, "total_chunk_count": total},
        }), "TikTok upload init")
        _raise_api_error(init, "TikTok upload init")
        data = init.get("data") or {}
        upload_url, publish_id = data.get("upload_url"), data.get("publish_id")
        if not upload_url or not publish_id:
            raise PlatformError("TikTok upload init returned no upload URL")

        # Sequential PUTs; the final chunk absorbs any trailing bytes.
        index, offset = 0, 0
        buffer = b""
        async for _, piece in read_chunks(media.path, chunk_size):
            buffer += piece
            if index < total - 1 and len(buffer) >= chunk_size:
                part, buffer = buffer[:chunk_size], buffer[chunk_size:]
                await self._put(upload_url, part, offset, media)
                offset += len(part)
                index += 1
        if buffer:
            await self._put(upload_url, buffer, offset, media)

        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            status = check(await self.http.post(f"{API}/post/publish/status/fetch/",
                                                headers={**JSON_HEADERS, **auth}, json={"publish_id": publish_id}),
                           "TikTok status")
            _raise_api_error(status, "TikTok status")
            sdata = status.get("data") or {}
            state = sdata.get("status")
            if state == "PUBLISH_COMPLETE":
                ids = sdata.get("publicaly_available_post_id") or []
                url = f"https://www.tiktok.com/@{account.get('username')}/video/{ids[0]}" if ids and account.get("username") else None
                return PublishResult(str(ids[0]) if ids else publish_id, url)
            if state == "FAILED":
                raise PlatformError(f"TikTok rejected the video: {sdata.get('fail_reason', 'unknown reason')}")
            await self.sleep(5)
        raise PlatformError("TikTok is still processing the video after 15 minutes")

    async def _put(self, url: str, part: bytes, offset: int, media: MediaFile) -> None:
        resp = await self.http.put(url, content=part, headers={
            "Content-Type": media.mime if media.mime in ("video/mp4", "video/quicktime", "video/webm") else "video/mp4",
            "Content-Length": str(len(part)),
            "Content-Range": f"bytes {offset}-{offset + len(part) - 1}/{media.size}",
        })
        if resp.status_code not in (200, 201, 206):
            raise PlatformError(f"TikTok chunk upload failed ({resp.status_code})")


def _raise_api_error(body: dict, what: str) -> None:
    err = body.get("error") or {}
    if isinstance(err, dict) and err.get("code") not in (None, "ok"):
        raise PlatformError(f"{what} failed: {err.get('code')} {err.get('message', '')}".strip())
