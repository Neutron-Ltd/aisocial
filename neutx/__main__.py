"""Run the NEUTX server: python -m neutx"""

import logging
import sys

import uvicorn

from .app import create_app
from .config import ConfigError, load_settings


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    print(f"NEUTX on http://{settings.host}:{settings.port}/  (ComfyUI: {settings.comfyui_url})")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, proxy_headers=False,
                log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
