"""X: OAuth 2.0 Authorization Code with PKCE + v2 chunked media upload."""

from __future__ import annotations

import time
from urllib.parse import urlencode

from .base import MediaFile, Platform, PlatformError, Profile, PublishResult, TokenSet, check, read_chunks

AUTH_URL = "https://x.com/i/oauth2/authorize"
API = "https://api.x.com/2"
SCOPES = "tweet.read tweet.write users.read media.write offline.access"
CHUNK = 4 * 1024 * 1024  # docs: keep segments at or below 5 MB


class X(Platform):
    key, label = "x", "X"
    media_kinds = frozenset({"video", "image"})
    uses_pkce = True
    caption_limit = 280

    def authorize_url(self, state: str, code_challenge: str) -> str:
        return AUTH_URL + "?" + urlencode({
            "response_type": "code",
            "client_id": self.creds.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        })

    async def _token(self, data: dict) -> TokenSet:
        body = check(await self.http.post(f"{API}/oauth2/token", data={"client_id": self.creds.client_id, **data},
                                          auth=(self.creds.client_id, self.creds.client_secret)),
                     "X token request")
        if "access_token" not in body:
            raise PlatformError("X token request returned no access token")
        return TokenSet(body["access_token"], body.get("refresh_token"), body.get("expires_in"), None,
                        body.get("scope", ""))

    async def exchange_code(self, code: str, code_verifier: str) -> tuple[TokenSet, Profile]:
        tokens = await self._token({"grant_type": "authorization_code", "code": code,
                                    "redirect_uri": self.redirect_uri, "code_verifier": code_verifier})
        me = check(await self.http.get(f"{API}/users/me", headers={"Authorization": f"Bearer {tokens.access_token}"}),
                   "X profile lookup").get("data") or {}
        if not me.get("id"):
            raise PlatformError("X did not return a user id")
        return tokens, Profile(str(me["id"]), me.get("username", ""))

    async def refresh(self, access_token: str, refresh_token: str | None) -> TokenSet:
        if not refresh_token:
            raise PlatformError("X connection has no refresh token; reconnect the account")
        return await self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    async def publish(self, access_token: str, account: dict, media: MediaFile, title: str, caption: str) -> PublishResult:
        auth = {"Authorization": f"Bearer {access_token}"}
        init = check(await self.http.post(f"{API}/media/upload/initialize", headers=auth, json={
            "media_type": media.mime,
            "total_bytes": media.size,
            "media_category": "tweet_video" if media.kind == "video" else "tweet_image",
        }), "X media init")
        media_id = (init.get("data") or {}).get("id")
        if not media_id:
            raise PlatformError("X media init returned no media id")

        segment = 0
        async for _, chunk in read_chunks(media.path, CHUNK):
            check(await self.http.post(f"{API}/media/upload/{media_id}/append", headers=auth,
                                       data={"segment_index": str(segment)},
                                       files={"media": ("chunk", chunk, "application/octet-stream")}),
                  "X media append")
            segment += 1

        final = check(await self.http.post(f"{API}/media/upload/{media_id}/finalize", headers=auth), "X media finalize")
        processing = (final.get("data") or {}).get("processing_info")
        deadline = time.monotonic() + 900
        while processing and processing.get("state") not in ("succeeded",):
            if processing.get("state") == "failed":
                err = processing.get("error") or {}
                raise PlatformError(f"X could not process the media: {err.get('message', 'unknown error')}")
            if time.monotonic() > deadline:
                raise PlatformError("X is still processing the media after 15 minutes")
            await self.sleep(max(1, int(processing.get("check_after_secs", 5))))
            status = check(await self.http.get(f"{API}/media/upload", headers=auth,
                                               params={"command": "STATUS", "media_id": media_id}), "X media status")
            processing = (status.get("data") or {}).get("processing_info")

        tweet = check(await self.http.post(f"{API}/tweets", headers=auth, json={
            "text": caption[: self.caption_limit], "media": {"media_ids": [str(media_id)]},
        }), "X post").get("data") or {}
        if not tweet.get("id"):
            raise PlatformError("X did not return a post id")
        user = account.get("username") or "i"
        return PublishResult(tweet["id"], f"https://x.com/{user}/status/{tweet['id']}")
