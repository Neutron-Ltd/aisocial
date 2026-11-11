"""FastAPI application: API routes, the static WebUI and the background worker."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, load_settings
from .routes import auth, content, social, system
from .services import Context, build_context, run_worker

log = logging.getLogger("neutx")

CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob: https:; media-src 'self' blob:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(settings: Settings | None = None, *, context: Context | None = None) -> FastAPI:
    settings = settings or (context.settings if context else load_settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx = context or build_context(settings)
        app.state.ctx = ctx
        stop = asyncio.Event()
        worker = asyncio.create_task(run_worker(ctx, stop)) if settings.worker_enabled else None
        try:
            yield
        finally:
            stop.set()
            if worker:
                await worker
            for task in list(ctx.tasks):
                task.cancel()
            await ctx.http.aclose()
            await ctx.comfy.aclose()

    app = FastAPI(title="NEUTX", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # CSRF: state-changing API calls must carry a custom header, which browsers
        # only allow cross-origin after a CORS preflight (which this app never grants).
        if request.method in UNSAFE_METHODS and request.url.path.startswith("/api/") \
                and request.headers.get("x-neutx") != "1":
            return JSONResponse({"detail": "missing X-NEUTX header"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
        return JSONResponse({"detail": f"{field}: {first.get('msg', 'invalid value')}"}, status_code=422)

    for module in (auth, content, social, system):
        app.include_router(module.router)
    app.mount("/", StaticFiles(directory=settings.webui_dir, html=True), name="webui")
    return app
