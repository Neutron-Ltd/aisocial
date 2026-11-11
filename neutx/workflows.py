"""Workflow files: ComfyUI API-format prompts with {{placeholder}} values.

Each file in WORKFLOWS_DIR is JSON of the form {"meta": {...}, "prompt": {...}}.
A string value that is exactly "{{name}}" is replaced with a typed value.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PLACEHOLDER_RE = re.compile(r"^\{\{([a-z_]+)\}\}$")
ASPECTS = ("9:16", "1:1", "16:9")
QUALITIES = ("draft", "standard")


class WorkflowError(ValueError):
    pass


@dataclass(frozen=True)
class Workflow:
    key: str
    meta: dict
    prompt: dict

    @property
    def kind(self) -> str:
        return self.meta.get("kind", "image")

    @property
    def image_input(self) -> str:
        return self.meta.get("image_input", "none")  # none | optional | required

    def public(self) -> dict:
        m = self.meta
        return {
            "key": self.key,
            "name": m.get("name", self.key),
            "engine": m.get("engine", ""),
            "kind": self.kind,
            "image_input": self.image_input,
            "description": m.get("description", ""),
            "models": m.get("models", {}),
            "aspects": [a for a in ASPECTS if a in m.get("sizes", {})],
            "lengths": list(m.get("lengths", {}).keys()),
            "sizes": {a: m["sizes"][a] for a in ASPECTS if a in m.get("sizes", {})},
        }

    def render(self, *, prompt: str, negative_prompt: str, aspect: str, quality: str,
               length: str | None, seed: int, image: str | None, filename_prefix: str) -> dict:
        m = self.meta
        sizes = m.get("sizes", {})
        if aspect not in sizes:
            raise WorkflowError(f"aspect ratio {aspect} is not supported by this workflow")
        if quality not in m.get("quality", {}):
            raise WorkflowError(f"quality {quality!r} is not supported by this workflow")
        if self.image_input == "required" and not image:
            raise WorkflowError("this workflow needs a hero image")
        width, height = sizes[aspect]
        values: dict[str, Any] = dict(m.get("defaults", {}))
        values.update(m["quality"][quality])
        lengths = m.get("lengths", {})
        if lengths:
            values["length"] = lengths.get(length or "standard") or next(iter(lengths.values()))
        values.update(prompt=prompt, negative_prompt=negative_prompt, width=width, height=height,
                      seed=seed, filename_prefix=filename_prefix)
        if image:
            values["image"] = image

        def sub(node: Any) -> Any:
            if isinstance(node, dict):
                return {k: sub(v) for k, v in node.items()}
            if isinstance(node, list):
                return [sub(v) for v in node]
            if isinstance(node, str):
                match = PLACEHOLDER_RE.match(node)
                if match:
                    name = match.group(1)
                    if name not in values:
                        raise WorkflowError(f"workflow {self.key} uses unknown placeholder {{{{{name}}}}}")
                    return values[name]
            return node

        return sub(copy.deepcopy(self.prompt))


class WorkflowRegistry:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()

    def _path(self, key: str) -> Path:
        if not KEY_RE.match(key):
            raise WorkflowError("invalid workflow key")
        path = (self.directory / f"{key}.json").resolve()
        if path.parent != self.directory:
            raise WorkflowError("invalid workflow key")
        return path

    def get(self, key: str) -> Workflow:
        path = self._path(key)
        if not path.is_file():
            raise WorkflowError(f"unknown workflow {key!r}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta, prompt = data["meta"], data["prompt"]
        except (ValueError, KeyError, TypeError) as exc:
            raise WorkflowError(f"workflow {key} is malformed: {exc}") from exc
        if not isinstance(prompt, dict) or not all(isinstance(n, dict) and "class_type" in n for n in prompt.values()):
            raise WorkflowError(f"workflow {key} prompt must be ComfyUI API format")
        return Workflow(key, meta, prompt)

    def list(self) -> list[Workflow]:
        out = []
        if self.directory.is_dir():
            for path in sorted(self.directory.glob("*.json")):
                try:
                    out.append(self.get(path.stem))
                except WorkflowError:
                    continue
        return out
