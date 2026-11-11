from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from neutx.platforms import Profile, TokenSet
from neutx.platforms.tiktok import chunk_plan
from neutx.services import process_due_posts, save_account
from tests.conftest import MP4_BYTES, png_bytes, signup


def connect(client, platform):
    """Run the real OAuth flow against the mocked platform."""
    r = client.post(f"/api/oauth/{platform}/start", json={"return_to": "connections.html"})
    assert r.status_code == 200, r.text
    url = urlsplit(r.json()["url"])
    qs = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert qs["state"] and qs["redirect_uri"] == f"https://neutx.example/api/oauth/{platform}/callback"
    cb = client.get(f"/api/oauth/{platform}/callback", params={"state": qs["state"], "code": "the-code"},
                    follow_redirects=False)
    assert cb.status_code == 303 and cb.headers["location"] == f"/connections.html?connected={platform}", cb.headers
    return qs


@pytest.mark.parametrize("platform,username", [("tiktok", "neutx_test"), ("youtube", "@neutx"),
                                                ("instagram", "neutx.ig"), ("x", "neutx_x")])
def test_oauth_connect(client, ctx, user, platform, username):
    qs = connect(client, platform)
    if platform == "x":
        assert qs["code_challenge_method"] == "S256" and len(qs["code_challenge"]) == 43
    accounts = client.get("/api/accounts").json()
    assert [(a["platform"], a["username"]) for a in accounts] == [(platform, username)]
    raw = ctx.db.one("SELECT access_token_enc FROM social_accounts")["access_token_enc"]
    assert "access" not in raw and "ig-long" not in raw  # stored encrypted


def test_oauth_rejects_bad_or_foreign_state(client, user):
    r = client.get("/api/oauth/x/callback", params={"state": "forged", "code": "c"}, follow_redirects=False)
    assert r.status_code == 303 and "error=" in r.headers["location"]
    url = urlsplit(client.post("/api/oauth/x/start", json={}).json()["url"])
    state = parse_qs(url.query)["state"][0]
    client.post("/api/auth/logout")
    signup(client, email="mallory@example.com")
    r = client.get("/api/oauth/x/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert "error=" in r.headers["location"]
    assert client.get("/api/accounts").json() == []


def test_oauth_callback_requires_login(client):
    r = client.get("/api/oauth/x/callback", params={"state": "s", "code": "c"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/auth.html?error=")


def test_chunk_plan_follows_tiktok_rules():
    assert chunk_plan(3_000_000) == (3_000_000, 1)
    assert chunk_plan(10 * 1024 * 1024) == (10 * 1024 * 1024, 1)
    size, count = chunk_plan(50_000_123)
    assert size == 10 * 1024 * 1024 and count == 4
    assert 50_000_123 - size * (count - 1) <= 128 * 1024 * 1024


def _video(client):
    return client.post("/api/media", files=[("files", ("clip.mp4", MP4_BYTES, "video/mp4"))]).json()["items"][0]


def _publish_all(client, ctx):
    """Run one scheduler pass and wait for the publish tasks it starts (on the portal's loop)."""
    async def run():
        import asyncio
        await asyncio.gather(*await process_due_posts(ctx))
    client.portal.call(run)


def test_publish_now_to_all_platforms(client, ctx, platforms_api, user):
    for p in ("tiktok", "youtube", "instagram", "x"):
        connect(client, p)
    accounts = {a["platform"]: a["id"] for a in client.get("/api/accounts").json()}
    video = _video(client)
    r = client.post("/api/posts", json={"media_id": video["id"], "account_ids": list(accounts.values()),
                                        "caption": "Hello #ai", "publish_now": True})
    assert r.status_code == 201, r.text
    _publish_all(client, ctx)
    post = client.get(f"/api/posts/{r.json()['id']}").json()
    assert post["status"] == "published", post
    urls = {t["platform"]: t["url"] for t in post["targets"]}
    assert urls["youtube"] == "https://www.youtube.com/watch?v=yt-video-1"
    assert urls["x"] == "https://x.com/neutx_x/status/1800000000000"
    assert urls["instagram"] == "https://www.instagram.com/reel/abc/"
    assert urls["tiktok"] == "https://www.tiktok.com/@neutx_test/video/7000001"
    assert platforms_api.uploaded["tiktok"] == len(MP4_BYTES) == platforms_api.uploaded["youtube"]
    # TikTok: AI-generated label set and configured privacy honoured
    import json
    init = json.loads(platforms_api.find("open.tiktokapis.com", "video/init")[0].content)
    assert init["post_info"]["is_aigc"] is True and init["post_info"]["privacy_level"] == "PUBLIC_TO_EVERYONE"
    assert init["post_info"]["disable_duet"] is True
    # YouTube: synthetic media disclosed
    yt = json.loads(platforms_api.find("www.googleapis.com", "upload", "POST")[0].content)
    assert yt["status"]["containsSyntheticMedia"] is True and yt["status"]["privacyStatus"] == "private"
    # Instagram fetched a signed public URL that serves the file, and tampering breaks it
    ig = json.loads(platforms_api.find("graph.instagram.com", "/media", "POST")[0].content)
    assert ig["media_type"] == "REELS"
    path = urlsplit(ig["video_url"]).path
    assert client.get(path, headers={"X-NEUTX": ""}).content == MP4_BYTES
    assert client.get(path[:-12] + "0" * 6 + path[-6:]).status_code == 404


def test_image_post_and_platform_validation(client, ctx, platforms_api, user):
    connect(client, "x")
    connect(client, "tiktok")
    accounts = {a["platform"]: a["id"] for a in client.get("/api/accounts").json()}
    img = client.post("/api/media", files=[("files", ("a.png", png_bytes(), "image/png"))]).json()["items"][0]
    r = client.post("/api/posts", json={"media_id": img["id"], "account_ids": [accounts["tiktok"]], "publish_now": True})
    assert r.status_code == 422 and "TikTok" in r.json()["detail"]
    r = client.post("/api/posts", json={"media_id": img["id"], "account_ids": [accounts["x"]], "caption": "pic",
                                        "publish_now": True})
    _publish_all(client, ctx)
    assert client.get(f"/api/posts/{r.json()['id']}").json()["status"] == "published"


def test_failure_is_recorded_and_retry_works(client, ctx, platforms_api, user):
    connect(client, "x")
    connect(client, "youtube")
    ids = [a["id"] for a in client.get("/api/accounts").json()]
    platforms_api.fail.add("x")
    r = client.post("/api/posts", json={"media_id": _video(client)["id"], "account_ids": ids, "publish_now": True})
    _publish_all(client, ctx)
    post = client.get(f"/api/posts/{r.json()['id']}").json()
    assert post["status"] == "partial"
    failed = next(t for t in post["targets"] if t["platform"] == "x")
    assert failed["status"] == "failed" and "not permitted" in failed["error"]
    platforms_api.fail.clear()
    assert client.post(f"/api/posts/{post['id']}/retry").json()["status"] == "scheduled"
    _publish_all(client, ctx)
    assert client.get(f"/api/posts/{post['id']}").json()["status"] == "published"
    assert len(platforms_api.find("www.googleapis.com", "upload", "POST")) == 1  # YouTube not re-posted


def test_schedule_reschedule_cancel_and_timezones(client, ctx, user):
    connect(client, "x")
    acc = client.get("/api/accounts").json()[0]["id"]
    tomorrow = (datetime.utcnow() + timedelta(days=2)).date().isoformat()
    r = client.post("/api/posts", json={"media_id": _video(client)["id"], "account_ids": [acc], "caption": "later",
                                        "date": tomorrow, "time": "15:00"})
    assert r.status_code == 201, r.text
    post = r.json()
    assert post["local_time"] == "15:00" and post["scheduled_at"].endswith("06:00:00Z")  # Asia/Tokyo is UTC+9
    assert client.get("/api/posts", params={"from": tomorrow, "to": tomorrow}).json()[0]["id"] == post["id"]
    assert client.portal.call(process_due_posts, ctx) == []  # not due yet
    later = (datetime.utcnow() + timedelta(days=4)).date().isoformat()
    moved = client.patch(f"/api/posts/{post['id']}", json={"date": later}).json()
    assert moved["local_date"] == later and moved["local_time"] == "15:00"
    assert client.post("/api/posts", json={"media_id": post["media"]["id"], "account_ids": [acc],
                                           "date": "2020-01-01", "time": "10:00"}).status_code == 422
    assert client.delete(f"/api/media/{post['media']['id']}").status_code == 409
    assert client.delete(f"/api/posts/{post['id']}").status_code == 204
    assert client.get("/api/posts").json() == []


def test_token_refresh_before_publish(client, ctx, platforms_api, user):
    save_account(ctx, user["id"], "youtube", TokenSet("old-access", "yt-refresh", expires_in=60), Profile("UC1", "c"))
    acc = client.get("/api/accounts").json()[0]["id"]
    r = client.post("/api/posts", json={"media_id": _video(client)["id"], "account_ids": [acc], "publish_now": True})
    _publish_all(client, ctx)
    assert client.get(f"/api/posts/{r.json()['id']}").json()["status"] == "published"
    upload = platforms_api.find("www.googleapis.com", "upload", "POST")[0]
    assert upload.headers["Authorization"] == "Bearer yt-access-2"


def test_instagram_requires_https_public_url(client, ctx, user, monkeypatch):
    connect(client, "instagram")
    object.__setattr__(ctx.settings, "public_base_url", "http://127.0.0.1:8080")
    acc = client.get("/api/accounts").json()[0]["id"]
    r = client.post("/api/posts", json={"media_id": _video(client)["id"], "account_ids": [acc], "publish_now": True})
    _publish_all(client, ctx)
    post = client.get(f"/api/posts/{r.json()['id']}").json()
    assert post["status"] == "failed" and "PUBLIC_BASE_URL" in post["targets"][0]["error"]


def test_unconfigured_platform(client, ctx, user):
    object.__setattr__(ctx.platforms["tiktok"].creds, "client_secret", "")
    r = client.post("/api/oauth/tiktok/start", json={})
    assert r.status_code == 409 and "not configured" in r.json()["detail"]
    assert next(p for p in client.get("/api/platforms").json() if p["key"] == "tiktok")["configured"] is False


def test_dashboard(client, ctx, user):
    connect(client, "x")
    d = client.get("/api/dashboard").json()
    assert d["stats"]["connected_accounts"] == 1 and d["upcoming"] == []
