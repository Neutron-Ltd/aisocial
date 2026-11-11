#!/usr/bin/env python3
"""Serve the NEUTX WebUI prototype locally.

Serves the static files in ../WebUI and generates /config.js from
environment variables so site-specific values never live in the repo.

Environment variables (see .env.example):
    WEBUI_HOST   Interface to bind (default: 127.0.0.1)
    WEBUI_PORT   Port to listen on (default: 8080)
    COMFYUI_URL  Base URL of your ComfyUI server (default: http://localhost:8188)

Only the Python standard library is used.
"""

import functools
import http.server
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

WEBUI_DIR = (Path(__file__).resolve().parent.parent / "WebUI").resolve()
DEFAULT_COMFYUI_URL = "http://localhost:8188"


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines; real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def validated_url(value: str) -> str:
    """Accept only plain http(s) origins; reject anything else."""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"COMFYUI_URL must be an http(s) URL, got {value!r}")
    if parts.username or parts.password:
        raise ValueError("COMFYUI_URL must not contain credentials")
    return f"{parts.scheme}://{parts.netloc}"


class WebUIHandler(http.server.SimpleHTTPRequestHandler):
    config_js = b""

    def do_GET(self):
        if urlsplit(self.path).path == "/config.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(self.config_js)))
            self.end_headers()
            self.wfile.write(self.config_js)
            return
        super().do_GET()

    def translate_path(self, path):
        # SimpleHTTPRequestHandler already strips '..' segments; additionally
        # refuse anything that resolves outside WEBUI_DIR (e.g. via symlinks).
        resolved = Path(super().translate_path(path)).resolve()
        if resolved != WEBUI_DIR and WEBUI_DIR not in resolved.parents:
            return str(WEBUI_DIR / "__forbidden__")
        return str(resolved)

    def list_directory(self, path):
        self.send_error(404, "Not found")
        return None

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    host = os.environ.get("WEBUI_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("WEBUI_PORT", "8080"))
        comfyui_url = validated_url(os.environ.get("COMFYUI_URL", DEFAULT_COMFYUI_URL))
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    config = {"comfyuiUrl": comfyui_url}
    # json.dumps output is valid JS; escape '<' so it can never close a tag.
    WebUIHandler.config_js = (
        "window.NEUTX_CONFIG = " + json.dumps(config).replace("<", "\\u003c") + ";\n"
    ).encode("utf-8")

    handler = functools.partial(WebUIHandler, directory=str(WEBUI_DIR))
    with http.server.ThreadingHTTPServer((host, port), handler) as httpd:
        print(f"Serving {WEBUI_DIR} at http://{host}:{port}/  (ComfyUI: {comfyui_url})")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
