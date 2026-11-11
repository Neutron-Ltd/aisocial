from __future__ import annotations

import base64
import io
import json
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from neutx.app import create_app
from neutx.config import load_settings
from neutx.services import build_context
from tests.fake_comfyui import create_fake_comfyui

BASE = "https://neutx.example"


def png_bytes(w=64, h=64, color=(200, 100, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


MP4_BYTES = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 2000


class FakePlatforms:
    """Mock of the four platform APIs. Records every request for assertions."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.uploaded: dict[str, int] = {}
        self.fail: set[str] = set()
        self.tiktok_status_polls = 0
        self.x_status_polls = 0

    def find(self, host: str, path_part: str = "", method: str | None = None) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == host and path_part in r.url.path
                and (method is None or r.method == method)]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path, m = request.url.host, request.url.path, request.method
        form = lambda: {k: v[0] for k, v in parse_qs(request.content.decode()).items()}  # noqa: E731
        body = lambda: json.loads(request.content or b"{}")  # noqa: E731
        J = httpx.Response  # noqa: N806

        # ---- TikTok
        if host == "open.tiktokapis.com":
            if path == "/v2/oauth/token/":
                f = form()
                assert f["client_key"] == "tt-key" and f["client_secret"] == "tt-secret"
                return J(200, json={"access_token": "tt-access", "refresh_token": "tt-refresh", "expires_in": 86400,
                                    "refresh_expires_in": 31536000, "open_id": "tt-open-id",
                                    "scope": "user.info.basic,video.publish", "token_type": "Bearer"})
            if path == "/v2/post/publish/creator_info/query/":
                return J(200, json={"data": {"creator_username": "neutx_test", "privacy_level_options":
                                             ["PUBLIC_TO_EVERYONE", "SELF_ONLY"], "comment_disabled": False,
                                             "duet_disabled": True, "stitch_disabled": False},
                                    "error": {"code": "ok"}})
            if path == "/v2/post/publish/video/init/":
                if "tiktok" in self.fail:
                    return J(403, json={"error": {"code": "unaudited_client_can_only_post_to_private_accounts",
                                                  "message": "unaudited"}})
                return J(200, json={"data": {"publish_id": "pub-1", "upload_url":
                                             "https://open-upload.tiktokapis.com/upload/?upload_id=1"},
                                    "error": {"code": "ok"}})
            if path == "/v2/post/publish/status/fetch/":
                self.tiktok_status_polls += 1
                status = "PROCESSING_UPLOAD" if self.tiktok_status_polls < 2 else "PUBLISH_COMPLETE"
                return J(200, json={"data": {"status": status, "publicaly_available_post_id": [7000001]},
                                    "error": {"code": "ok"}})
        if host == "open-upload.tiktokapis.com" and m == "PUT":
            rng = request.headers["Content-Range"]
            start, rest = rng.removeprefix("bytes ").split("-")
            end, total = rest.split("/")
            assert int(end) - int(start) + 1 == len(request.content) == int(request.headers["Content-Length"])
            self.uploaded["tiktok"] = int(end) + 1
            return J(201 if int(end) + 1 == int(total) else 206)

        # ---- Google / YouTube
        if host == "oauth2.googleapis.com" and path == "/token":
            f = form()
            assert f["client_id"] == "yt-id" and f["client_secret"] == "yt-secret"
            if f["grant_type"] == "refresh_token":
                return J(200, json={"access_token": "yt-access-2", "expires_in": 3599,
                                    "scope": "https://www.googleapis.com/auth/youtube.upload"})
            return J(200, json={"access_token": "yt-access", "refresh_token": "yt-refresh", "expires_in": 3599,
                                "scope": "https://www.googleapis.com/auth/youtube.upload "
                                         "https://www.googleapis.com/auth/youtube.readonly"})
        if host == "www.googleapis.com" and path == "/youtube/v3/channels":
            return J(200, json={"items": [{"id": "UC123", "snippet": {"title": "NEUTX Channel", "customUrl": "@neutx"}}]})
        if host == "www.googleapis.com" and path == "/upload/youtube/v3/videos":
            if m == "POST":
                assert request.headers["X-Upload-Content-Length"].isdigit()
                return J(200, headers={"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=abc"})
            rng = request.headers["Content-Range"]
            end, total = rng.removeprefix("bytes ").split("-")[1].split("/")
            self.uploaded["youtube"] = int(end) + 1
            if int(end) + 1 < int(total):
                return J(308, headers={"Range": f"bytes=0-{end}"})
            return J(200, json={"id": "yt-video-1"})

        # ---- Instagram
        if host == "api.instagram.com" and path == "/oauth/access_token":
            return J(200, json={"data": [{"access_token": "ig-short", "user_id": "ig-app-scoped",
                                          "permissions": "instagram_business_basic,instagram_business_content_publish"}]})
        if host == "graph.instagram.com":
            if path == "/access_token":
                return J(200, json={"access_token": "ig-long", "token_type": "bearer", "expires_in": 5184000})
            if path == "/refresh_access_token":
                return J(200, json={"access_token": "ig-long-2", "token_type": "bearer", "expires_in": 5184000})
            if path.endswith("/me"):
                return J(200, json={"data": [{"user_id": "17840000000", "username": "neutx.ig"}]})
            if path.endswith("/media") and m == "POST":
                return J(200, json={"id": "container-1"})
            if path.endswith("/container-1"):
                return J(200, json={"status_code": "FINISHED"})
            if path.endswith("/media_publish"):
                return J(200, json={"id": "ig-media-1"})
            if path.endswith("/ig-media-1"):
                return J(200, json={"permalink": "https://www.instagram.com/reel/abc/"})

        # ---- X
        if host == "api.x.com":
            if path == "/2/oauth2/token":
                expected = "Basic " + base64.b64encode(b"x-id:x-secret").decode()
                assert request.headers["Authorization"] == expected
                return J(200, json={"access_token": "x-access", "refresh_token": "x-refresh", "expires_in": 7200,
                                    "scope": "tweet.read tweet.write users.read media.write offline.access"})
            if path == "/2/users/me":
                return J(200, json={"data": {"id": "42", "username": "neutx_x"}})
            if path == "/2/media/upload/initialize":
                assert body()["media_category"] in ("tweet_video", "tweet_image")
                return J(200, json={"data": {"id": "m-1", "media_key": "13_m-1", "expires_after_secs": 86400}})
            if path == "/2/media/upload/m-1/append":
                return J(200, json={})
            if path == "/2/media/upload/m-1/finalize":
                return J(200, json={"data": {"id": "m-1", "processing_info": {"state": "pending", "check_after_secs": 1}}})
            if path == "/2/media/upload" and m == "GET":
                self.x_status_polls += 1
                return J(200, json={"data": {"id": "m-1", "processing_info": {"state": "succeeded"}}})
            if path == "/2/tweets":
                if "x" in self.fail:
                    return J(403, json={"title": "Forbidden", "detail": "You are not permitted to post"})
                assert body()["media"]["media_ids"] == ["m-1"]
                return J(201, json={"data": {"id": "1800000000000", "text": body()["text"]}})
        return httpx.Response(404, json={"error": f"unmocked {m} {request.url}"})


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for k, v in {
        "NEUTX_SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
        "DATA_DIR": str(tmp_path / "data"), "WORKER_ENABLED": "false", "PUBLIC_BASE_URL": BASE,
        "TIKTOK_CLIENT_ID": "tt-key", "TIKTOK_CLIENT_SECRET": "tt-secret",
        "YOUTUBE_CLIENT_ID": "yt-id", "YOUTUBE_CLIENT_SECRET": "yt-secret",
        "INSTAGRAM_CLIENT_ID": "ig-id", "INSTAGRAM_CLIENT_SECRET": "ig-secret",
        "X_CLIENT_ID": "x-id", "X_CLIENT_SECRET": "x-secret", "TIKTOK_PRIVACY_LEVEL": "PUBLIC_TO_EVERYONE",
    }.items():
        monkeypatch.setenv(k, v)
    return load_settings(env_file=None)


@pytest.fixture
def fake_comfy():
    return create_fake_comfyui(polls_until_done=2)


@pytest.fixture
def platforms_api():
    return FakePlatforms()


async def _no_sleep(_s):
    return None


@pytest.fixture
def app_ctx(settings, fake_comfy, platforms_api):
    ctx = build_context(settings, comfy_transport=httpx.ASGITransport(app=fake_comfy),
                        http_transport=httpx.MockTransport(platforms_api.handler), sleep=_no_sleep)
    app = create_app(context=ctx)
    with TestClient(app, base_url=BASE) as client:
        client.headers["X-NEUTX"] = "1"
        yield client, ctx


@pytest.fixture
def client(app_ctx):
    return app_ctx[0]


@pytest.fixture
def ctx(app_ctx):
    return app_ctx[1]


def signup(client, email="ana@example.com", password="correct horse battery", name="Ana"):
    r = client.post("/api/auth/signup", json={"email": email, "password": password, "name": name,
                                               "timezone": "Asia/Tokyo"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def user(client):
    return signup(client)
