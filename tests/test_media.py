from tests.conftest import MP4_BYTES, png_bytes, signup


def test_upload_list_download_delete(client, user):
    r = client.post("/api/media", files=[("files", ("../../etc/hero.png", png_bytes(32, 48), "image/png")),
                                         ("files", ("clip.mp4", MP4_BYTES, "video/mp4"))])
    assert r.status_code == 201, r.text
    items = r.json()["items"]
    assert [i["kind"] for i in items] == ["image", "video"]
    assert items[0]["original_name"] == "hero.png" and (items[0]["width"], items[0]["height"]) == (32, 48)
    listing = client.get("/api/media?kind=image").json()
    assert listing["total"] == 1 and listing["stats"]["count"] == 2
    assert client.get("/api/media?q=clip").json()["total"] == 1
    assert client.get(items[0]["url"]).content.startswith(b"\x89PNG")
    dl = client.get(items[0]["url"] + "?download=1")
    assert "attachment" in dl.headers["content-disposition"]
    assert client.delete(f"/api/media/{items[0]['id']}").status_code == 204
    assert client.get(items[0]["url"]).status_code == 404


def test_rejects_unknown_and_spoofed_files(client, user):
    r = client.post("/api/media", files=[("files", ("evil.png", b"<script>alert(1)</script>", "image/png"))])
    assert r.status_code == 422
    r = client.post("/api/media", files=[("files", ("x.png", b"\x89PNG\r\n\x1a\nnot really", "image/png"))])
    assert r.status_code == 422


def test_media_is_private(client, user):
    item = client.post("/api/media", files=[("files", ("a.png", png_bytes(), "image/png"))]).json()["items"][0]
    client.post("/api/auth/logout")
    assert client.get(item["url"]).status_code == 401
    signup(client, email="eve@example.com")
    assert client.get(item["url"]).status_code == 404
    assert client.delete(f"/api/media/{item['id']}").status_code == 404
    assert client.get("/api/media").json()["total"] == 0
