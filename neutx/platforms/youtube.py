"""YouTube: Google OAuth 2.0 (web server flow) + Data API v3 resumable upload."""

from __future__ import annotations

import re
from urllib.parse import urlencode

from .base import MediaFile, Platform, PlatformError, Profile, PublishResult, TokenSet, check, read_chunks

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
CHUNK = 32 * 256 * 1024  # 8 MiB, a multiple of 256 KiB as the API requires


def youtube_title(title: str, caption: str) -> str:
    text = (title or caption.split("\n", 1)[0] or "NEUTX video").replace("<", "").replace(">", "")
    text = re.sub(r"\s+", " ", text).strip() or "NEUTX video"
    return text[:100]


class YouTube(Platform):
    key, label = "youtube", "YouTube"
    caption_limit = 5000

    def authorize_url(self, state: str, code_challenge: str) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_id": self.creds.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        })

    async def _token(self, data: dict) -> TokenSet:
        body = check(await self.http.post(TOKEN_URL, data={
            "client_id": self.creds.client_id, "client_secret": self.creds.client_secret, **data,
        }), "Google token request")
        if "access_token" not in body:
            raise PlatformError("Google token request returned no access token")
        return TokenSet(body["access_token"], body.get("refresh_token"), body.get("expires_in"),
                        body.get("refresh_token_expires_in"), body.get("scope", ""))

    async def exchange_code(self, code: str, code_verifier: str) -> tuple[TokenSet, Profile]:
        tokens = await self._token({"code": code, "grant_type": "authorization_code", "redirect_uri": self.redirect_uri})
        if "youtube.upload" not in tokens.scope:
            raise PlatformError("Google did not grant the YouTube upload permission")
        body = check(await self.http.get(CHANNELS_URL, params={"part": "snippet", "mine": "true"},
                                         headers={"Authorization": f"Bearer {tokens.access_token}"}),
                     "YouTube channel lookup")
        items = body.get("items") or []
        if not items:
            raise PlatformError("this Google account has no YouTube channel")
        snippet = items[0].get("snippet") or {}
        return tokens, Profile(items[0]["id"], snippet.get("customUrl") or snippet.get("title", ""))

    async def refresh(self, access_token: str, refresh_token: str | None) -> TokenSet:
        if not refresh_token:
            raise PlatformError("YouTube connection has no refresh token; reconnect the account")
        tokens = await self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})
        tokens.refresh_token = tokens.refresh_token or refresh_token  # Google keeps the old one
        return tokens

    async def publish(self, access_token: str, account: dict, media: MediaFile, title: str, caption: str) -> PublishResult:
        if media.kind != "video":
            raise PlatformError("YouTube accepts videos only")
        auth = {"Authorization": f"Bearer {access_token}"}
        init = await self.http.post(
            UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
            headers={**auth, "Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Length": str(media.size), "X-Upload-Content-Type": media.mime},
            json={
                "snippet": {"title": youtube_title(title, caption), "description": caption[: self.caption_limit],
                            "categoryId": "22"},
                "status": {"privacyStatus": self.settings.youtube_privacy_status,
                           "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
            },
        )
        check(init, "YouTube upload session")
        session = init.headers.get("Location")
        if not session:
            raise PlatformError("YouTube did not return an upload session URL")

        result = None
        async for offset, chunk in read_chunks(media.path, CHUNK):
            end = offset + len(chunk) - 1
            resp = await self.http.put(session, content=chunk, headers={
                **auth, "Content-Length": str(len(chunk)), "Content-Range": f"bytes {offset}-{end}/{media.size}",
            })
            if resp.status_code == 308:
                continue
            result = check(resp, "YouTube upload")
        if not result or "id" not in result:
            raise PlatformError("YouTube upload finished without returning a video id")
        return PublishResult(result["id"], f"https://www.youtube.com/watch?v={result['id']}")
