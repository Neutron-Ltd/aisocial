"""ComfyUI status, dashboard summary and signed public media links."""

from __future__ import annotations

import re
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..comfyui import ComfyUIError
from ..db import iso, utcnow
from ..deps import current_user, get_ctx, user_zone
from ..services import Context
from .content import media_out, template_out
from .social import post_out

router = APIRouter(tags=["system"])


@router.get("/api/system/comfyui")
async def comfyui_status(models: bool = False, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    out: dict = {"url": ctx.settings.comfyui_url, "online": False}
    try:
        stats = await ctx.comfy.system_stats()
        queue = await ctx.comfy.queue()
    except ComfyUIError as exc:
        out["error"] = str(exc)
        return out
    system = stats.get("system", {})
    out.update(
        online=True,
        version=system.get("comfyui_version"),
        ram_total=system.get("ram_total"), ram_free=system.get("ram_free"),
        devices=[{k: d.get(k) for k in ("name", "type", "vram_total", "vram_free")} for d in stats.get("devices", [])],
        queue_running=len(queue.get("queue_running", [])), queue_pending=len(queue.get("queue_pending", [])),
    )
    if models:
        cache: dict[str, list[str] | None] = {}
        report = []
        for wf in ctx.workflows.list():
            missing = []
            for folder, files in wf.meta.get("models", {}).items():
                if folder not in cache:
                    try:
                        cache[folder] = await ctx.comfy.list_models(folder)
                    except ComfyUIError:
                        cache[folder] = None
                available = cache[folder]
                missing += [f"{folder}/{f}" for f in files if available is not None and f not in available]
            report.append({"key": wf.key, "name": wf.public()["name"], "missing": missing, "ready": not missing})
        out["workflows"] = report
    return out


@router.get("/api/dashboard")
def dashboard(user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    uid = user["id"]
    now = utcnow()
    week_ahead, week_ago = iso(now + timedelta(days=7)), iso(now - timedelta(days=7))
    one = lambda sql, *p: ctx.db.one(sql, (uid, *p))["n"]  # noqa: E731
    upcoming = ctx.db.all("SELECT * FROM posts WHERE user_id=? AND status IN ('scheduled','publishing')"
                          " ORDER BY scheduled_at LIMIT 5", (uid,))
    recent_media = ctx.db.all("SELECT * FROM media WHERE user_id=? ORDER BY id DESC LIMIT 4", (uid,))
    templates = ctx.db.all("SELECT * FROM templates WHERE user_id=? ORDER BY updated_at DESC LIMIT 3", (uid,))
    return {
        "today": now.astimezone(user_zone(user)).date().isoformat(),
        "stats": {
            "scheduled_next_7_days": one("SELECT COUNT(*) AS n FROM posts WHERE user_id=? AND status='scheduled'"
                                         " AND scheduled_at <= ?", week_ahead),
            "scheduled_total": one("SELECT COUNT(*) AS n FROM posts WHERE user_id=? AND status='scheduled'"),
            "published_last_7_days": one("SELECT COUNT(*) AS n FROM posts WHERE user_id=? AND status IN"
                                         " ('published','partial') AND scheduled_at >= ?", week_ago),
            "generated_last_7_days": one("SELECT COUNT(*) AS n FROM jobs WHERE user_id=? AND status='succeeded'"
                                         " AND created_at >= ?", week_ago),
            "active_jobs": one("SELECT COUNT(*) AS n FROM jobs WHERE user_id=? AND status IN"
                               " ('queued','submitted','running')"),
            "connected_accounts": one("SELECT COUNT(*) AS n FROM social_accounts WHERE user_id=?"),
            "failed_posts": one("SELECT COUNT(*) AS n FROM posts WHERE user_id=? AND status IN ('failed','partial')"),
        },
        "upcoming": [post_out(ctx, user, p) for p in upcoming],
        "recent_media": [media_out(m) for m in recent_media],
        "templates": [template_out(ctx, t) for t in templates],
    }


@router.get("/public/media/{media_id}/{exp}/{sig}/{name}", include_in_schema=False)
def public_media(media_id: int, exp: int, sig: str, name: str, ctx: Context = Depends(get_ctx)):
    """Time-limited signed link used by platforms (Instagram) that fetch media themselves."""
    if not re.fullmatch(r"[0-9a-f]{64}", sig) or exp < time.time() \
            or not ctx.crypto.verify(f"media:{media_id}:{exp}", sig):
        raise HTTPException(404, "not found")
    row = ctx.db.one("SELECT * FROM media WHERE id=?", (media_id,))
    if not row:
        raise HTTPException(404, "not found")
    if row["kind"] == "image":
        return FileResponse(ctx.media.jpeg_path(row), media_type="image/jpeg")
    return FileResponse(ctx.media.path(row["stored_name"]), media_type=row["mime"])
