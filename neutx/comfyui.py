"""Minimal async client for the ComfyUI HTTP API."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx


class ComfyUIError(RuntimeError):
    pass


@dataclass
class OutputFile:
    filename: str
    subfolder: str
    type: str


@dataclass
class PromptResult:
    done: bool
    success: bool
    outputs: list[OutputFile]
    error: str | None = None


class ComfyUIClient:
    def __init__(self, base_url: str, timeout_s: float = 30, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.client_id = uuid.uuid4().hex
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            return await self._http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise ComfyUIError(f"cannot reach ComfyUI at {self.base_url}: {exc.__class__.__name__}") from exc

    async def system_stats(self) -> dict:
        resp = await self._request("GET", "/system_stats")
        if resp.status_code != 200:
            raise ComfyUIError(f"ComfyUI /system_stats returned {resp.status_code}")
        return resp.json()

    async def list_models(self, folder: str) -> list[str] | None:
        """Model files ComfyUI sees in a folder (None if the folder type is unknown)."""
        resp = await self._request("GET", f"/models/{folder}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise ComfyUIError(f"ComfyUI /models/{folder} returned {resp.status_code}")
        return list(resp.json())

    async def queue(self) -> dict:
        resp = await self._request("GET", "/queue")
        if resp.status_code != 200:
            raise ComfyUIError(f"ComfyUI /queue returned {resp.status_code}")
        return resp.json()

    async def upload_image(self, filename: str, data: bytes, mime: str) -> str:
        resp = await self._request(
            "POST", "/upload/image",
            files={"image": (filename, data, mime)}, data={"overwrite": "true", "type": "input"},
        )
        if resp.status_code != 200:
            raise ComfyUIError(f"ComfyUI image upload failed ({resp.status_code})")
        body = resp.json()
        name = body.get("name")
        if not name:
            raise ComfyUIError("ComfyUI image upload returned no name")
        return f"{body['subfolder']}/{name}" if body.get("subfolder") else name

    async def submit(self, prompt: dict) -> str:
        resp = await self._request("POST", "/prompt", json={"prompt": prompt, "client_id": self.client_id})
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code != 200 or "prompt_id" not in body:
            raise ComfyUIError(_describe_prompt_error(body) or f"ComfyUI rejected the workflow ({resp.status_code})")
        return body["prompt_id"]

    async def is_pending(self, prompt_id: str) -> str | None:
        """Return 'running', 'queued', or None if the prompt is not in the queue."""
        q = await self.queue()
        for state, key in (("running", "queue_running"), ("queued", "queue_pending")):
            for item in q.get(key, []):
                if len(item) > 1 and item[1] == prompt_id:
                    return state
        return None

    async def result(self, prompt_id: str) -> PromptResult:
        resp = await self._request("GET", f"/history/{prompt_id}")
        if resp.status_code != 200:
            raise ComfyUIError(f"ComfyUI /history returned {resp.status_code}")
        entry = resp.json().get(prompt_id)
        if not entry:
            return PromptResult(done=False, success=False, outputs=[])
        status = entry.get("status") or {}
        status_str = status.get("status_str")
        done = status.get("completed") or status_str in ("success", "error") or (not status and entry.get("outputs"))
        if not done:
            return PromptResult(done=False, success=False, outputs=[])
        if status_str == "error":
            return PromptResult(done=True, success=False, outputs=[], error=_describe_history_error(status))
        files: list[OutputFile] = []
        for node_output in (entry.get("outputs") or {}).values():
            for items in node_output.values():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict) and item.get("filename") and item.get("type") == "output":
                        files.append(OutputFile(item["filename"], item.get("subfolder", ""), "output"))
        return PromptResult(done=True, success=True, outputs=files)

    async def download(self, f: OutputFile) -> bytes:
        resp = await self._request(
            "GET", "/view", params={"filename": f.filename, "subfolder": f.subfolder, "type": f.type}
        )
        if resp.status_code != 200:
            raise ComfyUIError(f"ComfyUI /view returned {resp.status_code} for {f.filename}")
        return resp.content


def _describe_prompt_error(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    err = body.get("error")
    parts = []
    if isinstance(err, dict):
        parts.append(err.get("message") or err.get("type") or "")
    elif err:
        parts.append(str(err))
    for node_id, node_err in (body.get("node_errors") or {}).items():
        for e in node_err.get("errors", [])[:3]:
            parts.append(f"node {node_id} ({node_err.get('class_type', '?')}): {e.get('details') or e.get('message')}")
    text = "; ".join(p for p in parts if p)
    return text[:1000] or None


def _describe_history_error(status: dict) -> str:
    for kind, data in reversed(status.get("messages") or []):
        if kind == "execution_error" and isinstance(data, dict):
            return f"{data.get('node_type', 'node')}: {data.get('exception_message', 'execution failed')}"[:1000]
    return "ComfyUI reported an execution error"
