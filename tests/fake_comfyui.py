"""A fake ComfyUI server for tests and local development without a GPU.

It implements the subset of the ComfyUI HTTP API that NEUTX uses, validates
submitted workflows (known node types, no unresolved {{placeholders}}, uploaded
images exist) and returns real PNG images and H.264 MP4 videos that render the
prompt text, so the whole app can be exercised end to end.

Run standalone:  python tests/fake_comfyui.py --port 8188
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import tempfile
import textwrap
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw

KNOWN_NODES = {
    "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage", "EmptySD3LatentImage", "KSampler",
    "VAEDecode", "SaveImage", "FluxGuidance", "UNETLoader", "ModelSamplingSD3", "CLIPLoader", "VAELoader",
    "EmptyHunyuanLatentVideo", "CLIPVisionLoader", "LoadImage", "CLIPVisionEncode", "WanImageToVideo",
    "CreateVideo", "SaveVideo",
}
WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"


def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _frame(width: int, height: int, text: str, t: float) -> Image.Image:
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(0, height, 4):
        k = y / max(height, 1)
        draw.rectangle([0, y, width, y + 4], fill=(int(25 + 60 * k), int(25 + 40 * t), int(35 + 120 * (1 - k))))
    r = min(width, height) // 6
    cx, cy = int(width * (0.2 + 0.6 * t)), height // 3
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(229, 185, 108))
    lines = textwrap.wrap(text, width=max(12, width // 9))[:8]
    for i, line in enumerate(lines):
        draw.text((16, height // 2 + i * 14), line, fill=(248, 250, 252))
    draw.text((16, 16), "FAKE COMFYUI OUTPUT", fill=(249, 217, 140))
    return img


def render_png(width: int, height: int, text: str) -> bytes:
    buf = io.BytesIO()
    _frame(width, height, text, 0.5).save(buf, "PNG")
    return buf.getvalue()


def render_mp4(width: int, height: int, frames: int, fps: float, text: str) -> bytes:
    exe = _ffmpeg()
    if not exe:  # minimal ISO-BMFF header so the app still recognises it as MP4
        return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 64
    frames = max(8, min(frames, 48))
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(frames):
            _frame(width, height, text, i / (frames - 1)).save(f"{tmp}/f{i:03d}.png")
        out = f"{tmp}/out.mp4"
        subprocess.run([exe, "-loglevel", "error", "-y", "-framerate", str(fps), "-i", f"{tmp}/f%03d.png",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
        return Path(out).read_bytes()


def create_fake_comfyui(*, polls_until_done: int = 2, fail_execution: bool = False,
                        missing_models: set[str] | None = None) -> FastAPI:
    app = FastAPI()
    state = {"prompts": {}, "inputs": {}, "outputs": {}, "counter": 0}
    missing_models = missing_models or set()

    def node_error(node_id: str, node: dict, message: str) -> JSONResponse:
        return JSONResponse({"error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation"},
                             "node_errors": {node_id: {"class_type": node.get("class_type"),
                                                       "errors": [{"message": message, "details": message}]}}},
                            status_code=400)

    @app.get("/system_stats")
    def system_stats():
        return {"system": {"os": "fake", "ram_total": 64 * 2**30, "ram_free": 40 * 2**30, "comfyui_version": "0.19.3-fake"},
                "devices": [{"name": "Fake GPU", "type": "cuda", "index": 0, "vram_total": 24 * 2**30,
                             "vram_free": 18 * 2**30}]}

    @app.get("/models/{folder}")
    def models(folder: str):
        files = set()
        for path in WORKFLOWS_DIR.glob("*.json"):
            files.update(json.loads(path.read_text())["meta"].get("models", {}).get(folder, []))
        return sorted(f for f in files if f"{folder}/{f}" not in missing_models)

    @app.get("/queue")
    def queue():
        pending = [[i, pid, {}, {}, []] for i, (pid, p) in enumerate(state["prompts"].items()) if not p["done"]]
        return {"queue_running": pending[:1], "queue_pending": pending[1:]}

    @app.post("/upload/image")
    async def upload(image: UploadFile = File(...), overwrite: str = Form("false"), type: str = Form("input")):
        data = await image.read()
        Image.open(io.BytesIO(data)).verify()
        state["inputs"][image.filename] = data
        return {"name": image.filename, "subfolder": "", "type": "input"}

    @app.post("/prompt")
    async def prompt(body: dict):
        graph = body.get("prompt")
        if not isinstance(graph, dict) or not graph:
            return JSONResponse({"error": {"message": "no prompt"}, "node_errors": {}}, status_code=400)
        for node_id, node in graph.items():
            if node.get("class_type") not in KNOWN_NODES:
                return node_error(node_id, node, f"unknown node type {node.get('class_type')}")
            for key, value in node.get("inputs", {}).items():
                if isinstance(value, str) and "{{" in value:
                    return node_error(node_id, node, f"unresolved placeholder in {key}")
                if isinstance(value, list) and (len(value) != 2 or str(value[0]) not in graph):
                    return node_error(node_id, node, f"bad link in {key}")
            if node["class_type"] == "LoadImage" and node["inputs"]["image"] not in state["inputs"]:
                return node_error(node_id, node, "image not uploaded")
        pid = uuid.uuid4().hex
        state["prompts"][pid] = {"graph": graph, "polls": 0, "done": False}
        return {"prompt_id": pid, "number": len(state["prompts"]), "node_errors": {}}

    def _execute(pid: str) -> dict:
        graph = state["prompts"][pid]["graph"]
        text = next((n["inputs"]["text"] for n in graph.values() if n["class_type"] == "CLIPTextEncode"
                     and n["inputs"].get("text")), "")
        size = next((n["inputs"] for n in graph.values() if n["class_type"] in
                     ("EmptyLatentImage", "EmptySD3LatentImage", "EmptyHunyuanLatentVideo", "WanImageToVideo")), {})
        w, h = int(size.get("width", 512)), int(size.get("height", 512))
        outputs = {}
        for node_id, node in graph.items():
            prefix = node["inputs"].get("filename_prefix", "ComfyUI")
            state["counter"] += 1
            if node["class_type"] == "SaveImage":
                name = f"{Path(prefix).name}_{state['counter']:05}_.png"
                state["outputs"][name] = render_png(w, h, text)
                outputs[node_id] = {"images": [{"filename": name, "subfolder": str(Path(prefix).parent), "type": "output"}]}
            elif node["class_type"] == "SaveVideo":
                fps = float(graph[node["inputs"]["video"][0]]["inputs"].get("fps", 16))
                name = f"{Path(prefix).name}_{state['counter']:05}_.mp4"
                state["outputs"][name] = render_mp4(w, h, int(size.get("length", 33)), fps, text)
                outputs[node_id] = {"images": [{"filename": name, "subfolder": str(Path(prefix).parent), "type": "output"}],
                                    "animated": [True]}
        return outputs

    @app.get("/history/{pid}")
    def history(pid: str):
        p = state["prompts"].get(pid)
        if not p:
            return {}
        p["polls"] += 1
        if p["polls"] < polls_until_done:
            return {}
        p["done"] = True
        if fail_execution:
            return {pid: {"outputs": {}, "status": {"status_str": "error", "completed": False, "messages": [
                ["execution_error", {"node_type": "KSampler", "exception_message": "CUDA out of memory (fake)"}]]}}}
        if "outputs" not in p:
            p["outputs"] = _execute(pid)
        return {pid: {"outputs": p["outputs"], "status": {"status_str": "success", "completed": True, "messages": []}}}

    @app.get("/view")
    def view(filename: str, subfolder: str = "", type: str = "output"):
        data = state["outputs"].get(Path(filename).name)
        if data is None:
            return Response(status_code=404)
        media = "video/mp4" if filename.endswith(".mp4") else "image/png"
        return Response(data, media_type=media)

    app.state.fake = state
    return app


app = create_fake_comfyui(polls_until_done=3)

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8188)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
