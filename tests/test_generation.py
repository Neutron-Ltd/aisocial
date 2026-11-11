import json
from pathlib import Path

import pytest

from neutx.services import process_jobs
from neutx.workflows import WorkflowRegistry
from tests.conftest import png_bytes, signup
from tests.fake_comfyui import KNOWN_NODES

WORKFLOWS = Path(__file__).resolve().parent.parent / "workflows"


@pytest.mark.parametrize("key", [p.stem for p in WORKFLOWS.glob("*.json")])
def test_bundled_workflows_render(key):
    wf = WorkflowRegistry(WORKFLOWS).get(key)
    for aspect in wf.public()["aspects"]:
        rendered = wf.render(prompt="a cat", negative_prompt="blurry", aspect=aspect, quality="standard",
                             length="short", seed=7, image="hero.png", filename_prefix="neutx/job_1")
        text = json.dumps(rendered)
        assert "{{" not in text
        for node_id, node in rendered.items():
            assert node["class_type"] in KNOWN_NODES
            for value in node["inputs"].values():
                if isinstance(value, list):
                    assert str(value[0]) in rendered, f"{key}: node {node_id} links to missing node"
        w, h = wf.meta["sizes"][aspect]
        assert w % 16 == 0 and h % 16 == 0


def test_workflow_key_cannot_escape_directory(tmp_path):
    reg = WorkflowRegistry(WORKFLOWS)
    for bad in ("../config", "..", "a/b", "/etc/passwd", "UPPER"):
        with pytest.raises(ValueError):
            reg.get(bad)


def _run(client, ctx, times=3):
    for _ in range(times):
        client.portal.call(process_jobs, ctx)


def test_text_to_image_job(client, ctx, user):
    templates = client.get("/api/templates").json()
    tpl = next(t for t in templates if t["workflow"] == "flux_dev_image")
    r = client.post("/api/jobs", json={"template_id": tpl["id"], "prompt": "neon city at night", "quality": "draft"})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "queued" and "neon city at night" in job["prompt"] and tpl["style_prompt"] in job["prompt"]
    _run(client, ctx)
    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "succeeded", job
    assert len(job["outputs"]) == 1 and job["outputs"][0]["kind"] == "image"
    out = job["outputs"][0]
    assert (out["width"], out["height"]) == (1024, 1024)
    f = client.get(out["url"])
    assert f.status_code == 200 and f.content.startswith(b"\x89PNG")


def test_image_to_video_job_uploads_hero(client, ctx, fake_comfy, user):
    hero = client.post("/api/media", files=[("files", ("hero.png", png_bytes(), "image/png"))]).json()["items"][0]
    tpl = next(t for t in client.get("/api/templates").json() if t["workflow"] == "wan21_i2v")
    assert client.post("/api/jobs", json={"template_id": tpl["id"], "prompt": "slow push in"}).status_code == 422
    r = client.post("/api/jobs", json={"template_id": tpl["id"], "prompt": "slow push in", "length": "short",
                                       "image_media_id": hero["id"]})
    assert r.status_code == 201, r.text
    _run(client, ctx)
    job = client.get(f"/api/jobs/{r.json()['id']}").json()
    assert job["status"] == "succeeded", job
    assert job["outputs"][0]["kind"] == "video" and job["outputs"][0]["mime"] == "video/mp4"
    assert len(fake_comfy.state.fake["inputs"]) == 1


def test_failed_execution_is_reported(settings, platforms_api):
    import httpx
    from fastapi.testclient import TestClient

    from neutx.app import create_app
    from neutx.services import build_context
    from tests.fake_comfyui import create_fake_comfyui

    ctx = build_context(settings, comfy_transport=httpx.ASGITransport(app=create_fake_comfyui(fail_execution=True)))
    with TestClient(create_app(context=ctx), base_url="https://neutx.example") as client:
        client.headers["X-NEUTX"] = "1"
        signup(client)
        tpl = client.get("/api/templates").json()[0]
        job = client.post("/api/jobs", json={"template_id": tpl["id"], "prompt": "x"}).json()
        _run(client, ctx)
        job = client.get(f"/api/jobs/{job['id']}").json()
        assert job["status"] == "failed" and "out of memory" in job["error"]


def test_comfyui_offline_keeps_job_queued(settings):
    import httpx
    from fastapi.testclient import TestClient

    from neutx.app import create_app
    from neutx.services import build_context

    def offline(request):
        raise httpx.ConnectError("refused")

    ctx = build_context(settings, comfy_transport=httpx.MockTransport(offline))
    with TestClient(create_app(context=ctx), base_url="https://neutx.example") as client:
        client.headers["X-NEUTX"] = "1"
        signup(client)
        tpl = client.get("/api/templates").json()[0]
        job = client.post("/api/jobs", json={"template_id": tpl["id"], "prompt": "x"}).json()
        _run(client, ctx, 1)
        job = client.get(f"/api/jobs/{job['id']}").json()
        assert job["status"] == "queued" and job["error"].startswith("Waiting for ComfyUI")
        status = client.get("/api/system/comfyui").json()
        assert status["online"] is False


def test_comfyui_status_reports_models(client, user):
    status = client.get("/api/system/comfyui?models=true").json()
    assert status["online"] and status["devices"][0]["name"] == "Fake GPU"
    assert all(w["ready"] for w in status["workflows"])


def test_templates_crud_and_isolation(client, user):
    r = client.post("/api/templates", json={"name": "Mine", "workflow": "sd15_image", "aspect": "1:1",
                                            "style_prompt": "watercolor"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert client.post("/api/templates", json={"name": "Bad", "workflow": "../etc"}).status_code == 422
    assert client.put(f"/api/templates/{tid}", json={"name": "Mine 2", "workflow": "sd15_image",
                                                     "aspect": "16:9"}).json()["name"] == "Mine 2"
    system = next(t for t in client.get("/api/templates").json() if t["system"])
    assert client.delete(f"/api/templates/{system['id']}").status_code == 403
    client.post("/api/auth/logout")
    signup(client, email="other@example.com")
    assert client.get(f"/api/templates/{tid}").status_code == 404
    assert client.delete(f"/api/templates/{tid}").status_code == 404
