"""Instagram API with Instagram Login: Reels and single-image posts.

Instagram fetches the media itself, so PUBLIC_BASE_URL must be a public
https URL that Instagram can reach. Media is exposed through short-lived
signed links only for the duration of the publish attempt.
"""

from __future__ import annotations

import time
from urllib.parse import urlencode

from .base import MediaFile, Platform, PlatformError, Profile, PublishResult, TokenSet, check

AUTH_URL = "https://www.instagram.com/oauth/authorize"
SHORT_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH = "https://graph.instagram.com"
GRAPH_VERSION = "v27.0"
SCOPES = "instagram_business_basic,instagram_business_content_publish"


def _unwrap(body: dict) -> dict:
    """Some Instagram endpoints wrap the payload as {"data": [{...}]}."""
    data = body.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return body


class Instagram(Platform):
    key, label = "instagram", "Instagram"
    media_kinds = frozenset({"video", "image"})
    caption_limit = 2200

    def authorize_url(self, state: str, code_challenge: str) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_id": self.creds.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
        })

    async def exchange_code(self, code: str, code_verifier: str) -> tuple[TokenSet, Profile]:
        short = _unwrap(check(await self.http.post(SHORT_TOKEN_URL, data={
            "client_id": self.creds.client_id, "client_secret": self.creds.client_secret,
            "grant_type": "authorization_code", "redirect_uri": self.redirect_uri, "code": code.rstrip("#_"),
        }), "Instagram token request"))
        if "access_token" not in short:
            raise PlatformError("Instagram token request returned no access token")
        long_lived = check(await self.http.get(f"{GRAPH}/access_token", params={
            "grant_type": "ig_exchange_token", "client_secret": self.creds.client_secret,
            "access_token": short["access_token"],
        }), "Instagram long-lived token exchange")
        tokens = TokenSet(long_lived["access_token"], None, long_lived.get("expires_in"), None,
                          str(short.get("permissions", "")))
        me = _unwrap(check(await self.http.get(f"{GRAPH}/{GRAPH_VERSION}/me", params={
            "fields": "user_id,username", "access_token": tokens.access_token,
        }), "Instagram profile lookup"))
        if not me.get("user_id"):
            raise PlatformError("Instagram did not return a professional account id")
        return tokens, Profile(str(me["user_id"]), me.get("username", ""))

    def needs_refresh(self, seconds_left: float | None, age_s: float) -> bool:
        # Long-lived tokens last ~60 days and can be refreshed once they are 24h old.
        return seconds_left is not None and seconds_left < 7 * 86400 and age_s > 86400

    async def refresh(self, access_token: str, refresh_token: str | None) -> TokenSet:
        body = check(await self.http.get(f"{GRAPH}/refresh_access_token", params={
            "grant_type": "ig_refresh_token", "access_token": access_token,
        }), "Instagram token refresh")
        return TokenSet(body["access_token"], None, body.get("expires_in"))

    async def publish(self, access_token: str, account: dict, media: MediaFile, title: str, caption: str) -> PublishResult:
        if not self.settings.public_is_https or media.public_url is None:
            raise PlatformError("Instagram needs PUBLIC_BASE_URL set to a public https URL it can download media from")
        auth = {"Authorization": f"Bearer {access_token}"}
        ig_id = account["external_id"]
        payload = {"caption": caption[: self.caption_limit]}
        if media.kind == "video":
            payload.update(media_type="REELS", video_url=media.public_url())
        else:
            payload.update(image_url=media.public_url())
        container = check(await self.http.post(f"{GRAPH}/{GRAPH_VERSION}/{ig_id}/media", headers=auth, json=payload),
                          "Instagram media container")
        creation_id = container.get("id")
        if not creation_id:
            raise PlatformError("Instagram did not return a media container id")

        deadline = time.monotonic() + 600
        while True:
            status = check(await self.http.get(f"{GRAPH}/{GRAPH_VERSION}/{creation_id}",
                                               params={"fields": "status_code"}, headers=auth),
                           "Instagram container status").get("status_code")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise PlatformError(f"Instagram could not process the media (status {status})")
            if time.monotonic() > deadline:
                raise PlatformError("Instagram is still processing the media after 10 minutes")
            await self.sleep(15)

        published = check(await self.http.post(f"{GRAPH}/{GRAPH_VERSION}/{ig_id}/media_publish", headers=auth,
                                               json={"creation_id": creation_id}), "Instagram publish")
        media_id = published.get("id")
        if not media_id:
            raise PlatformError("Instagram publish returned no media id")
        link = None
        try:
            link = check(await self.http.get(f"{GRAPH}/{GRAPH_VERSION}/{media_id}", params={"fields": "permalink"},
                                             headers=auth), "Instagram permalink").get("permalink")
        except PlatformError:
            pass
        return PublishResult(str(media_id), link)
