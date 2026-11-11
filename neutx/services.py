"""Application context, account token handling and the background worker."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import quote

import httpx

from .comfyui import ComfyUIClient, ComfyUIError
from .config import Settings
from .db import Database, iso, now_iso, parse_iso, utcnow
from .media import MediaError, MediaStore
from .platforms import MediaFile, Platform, PlatformError, Profile, TokenSet, build_platforms
from .security import Crypto, RateLimiter
from .workflows import WorkflowError, WorkflowRegistry

log = logging.getLogger("neutx")

SYSTEM_TEMPLATES = [
    {"slug": "vertical-trend", "name": "TikTok / Reels Trend", "workflow": "wan21_t2v", "aspect": "9:16",
     "description": "Vertical 9:16 short-form clip from a text prompt.",
     "style_prompt": "dynamic camera movement, vibrant colors, trending social media style",
     "negative_prompt": "blurry, low quality, static, watermark, text, distorted"},
    {"slug": "cinematic-broll", "name": "Cinematic B-Roll", "workflow": "wan21_i2v", "aspect": "16:9",
     "description": "Animates your hero image into a 16:9 cinematic shot.",
     "style_prompt": "cinematic lighting, slow camera push-in, film grain, shallow depth of field",
     "negative_prompt": "blurry, low quality, jitter, watermark, text, deformed"},
    {"slug": "static-image", "name": "Static Image Post", "workflow": "flux_dev_image", "aspect": "1:1",
     "description": "High-resolution still image for X or the Instagram grid.",
     "style_prompt": "highly detailed, sharp focus, professional photography",
     "negative_prompt": ""},
]


@dataclass
class Context:
    settings: Settings
    db: Database
    crypto: Crypto
    media: MediaStore
    workflows: WorkflowRegistry
    comfy: ComfyUIClient
    http: httpx.AsyncClient
    platforms: dict[str, Platform]
    tasks: set = field(default_factory=set)
    login_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(limit=10, window_s=300))
    signup_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(limit=5, window_s=3600))


def build_context(settings: Settings, *, comfy_transport=None, http_transport=None, sleep=asyncio.sleep) -> Context:
    db = Database(settings.db_path)
    http = httpx.AsyncClient(timeout=httpx.Timeout(60, write=300, read=300), transport=http_transport,
                             headers={"User-Agent": "neutx/1.0"})
    ctx = Context(
        settings=settings,
        db=db,
        crypto=Crypto(settings.secret_key),
        media=MediaStore(db, settings.media_dir),
        workflows=WorkflowRegistry(settings.workflows_dir),
        comfy=ComfyUIClient(settings.comfyui_url, settings.comfyui_timeout_s, transport=comfy_transport),
        http=http,
        platforms=build_platforms(settings, http, sleep=sleep),
    )
    seed_system_templates(ctx)
    return ctx


def seed_system_templates(ctx: Context) -> None:
    now = now_iso()
    for t in SYSTEM_TEMPLATES:
        ctx.db.execute(
            "INSERT INTO templates (user_id, slug, name, description, workflow, aspect, style_prompt, negative_prompt,"
            " created_at, updated_at) VALUES (NULL,?,?,?,?,?,?,?,?,?) ON CONFLICT(slug) DO NOTHING",
            (t["slug"], t["name"], t["description"], t["workflow"], t["aspect"], t["style_prompt"],
             t["negative_prompt"], now, now),
        )


# --------------------------------------------------------------------------- accounts

def _expiry(seconds: int | None) -> str | None:
    return iso(utcnow() + timedelta(seconds=int(seconds))) if seconds else None


def save_account(ctx: Context, user_id: int, platform: str, tokens: TokenSet, profile: Profile) -> int:
    now = now_iso()
    enc = ctx.crypto.encrypt
    ctx.db.execute(
        "INSERT INTO social_accounts (user_id, platform, external_id, username, access_token_enc, refresh_token_enc,"
        " expires_at, refresh_expires_at, scope, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(user_id, platform, external_id) DO UPDATE SET username=excluded.username,"
        " access_token_enc=excluded.access_token_enc,"
        " refresh_token_enc=COALESCE(excluded.refresh_token_enc, social_accounts.refresh_token_enc),"
        " expires_at=excluded.expires_at, refresh_expires_at=excluded.refresh_expires_at, scope=excluded.scope,"
        " updated_at=excluded.updated_at",
        (user_id, platform, profile.external_id, profile.username, enc(tokens.access_token),
         enc(tokens.refresh_token) if tokens.refresh_token else None, _expiry(tokens.expires_in),
         _expiry(tokens.refresh_expires_in), tokens.scope, now, now),
    )
    row = ctx.db.one("SELECT id FROM social_accounts WHERE user_id=? AND platform=? AND external_id=?",
                     (user_id, platform, profile.external_id))
    return row["id"]


async def access_token_for(ctx: Context, account: dict) -> str:
    platform = ctx.platforms[account["platform"]]
    access = ctx.crypto.decrypt(account["access_token_enc"])
    refresh = ctx.crypto.decrypt(account["refresh_token_enc"]) if account["refresh_token_enc"] else None
    seconds_left = None
    if account["expires_at"]:
        seconds_left = (parse_iso(account["expires_at"]) - utcnow()).total_seconds()
    age = (utcnow() - parse_iso(account["updated_at"])).total_seconds()
    if not platform.needs_refresh(seconds_left, age):
        return access
    tokens = await platform.refresh(access, refresh)
    ctx.db.execute(
        "UPDATE social_accounts SET access_token_enc=?, refresh_token_enc=COALESCE(?, refresh_token_enc),"
        " expires_at=?, refresh_expires_at=COALESCE(?, refresh_expires_at), updated_at=? WHERE id=?",
        (ctx.crypto.encrypt(tokens.access_token),
         ctx.crypto.encrypt(tokens.refresh_token) if tokens.refresh_token else None,
         _expiry(tokens.expires_in), _expiry(tokens.refresh_expires_in), now_iso(), account["id"]),
    )
    return tokens.access_token


def public_media_url(ctx: Context, media: dict, ttl_s: int = 3600) -> str:
    exp = int(time.time()) + ttl_s
    sig = ctx.crypto.sign(f"media:{media['id']}:{exp}")
    ext = "jpg" if media["kind"] == "image" else media["stored_name"].rsplit(".", 1)[1]
    name = quote("neutx-{}.{}".format(media["id"], ext))
    return f"{ctx.settings.public_base_url}/public/media/{media['id']}/{exp}/{sig}/{name}"


# --------------------------------------------------------------------------- generation jobs

def _job_params(job: dict) -> dict:
    return json.loads(job["params"] or "{}")


async def _submit_job(ctx: Context, job: dict) -> None:
    params = _job_params(job)
    workflow = ctx.workflows.get(job["workflow"])
    image_name = None
    if job["input_media_id"]:
        media = ctx.db.one("SELECT * FROM media WHERE id=? AND user_id=?", (job["input_media_id"], job["user_id"]))
        if not media or media["kind"] != "image":
            raise WorkflowError("the hero image no longer exists")
        data = await asyncio.to_thread(ctx.media.path(media["stored_name"]).read_bytes)
        image_name = await ctx.comfy.upload_image(f"neutx_{media['stored_name']}", data, media["mime"])
    prompt = workflow.render(
        prompt=job["prompt"], negative_prompt=params.get("negative_prompt", ""), aspect=params["aspect"],
        quality=params["quality"], length=params.get("length"), seed=params["seed"], image=image_name,
        filename_prefix=f"neutx/job_{job['id']}",
    )
    prompt_id = await ctx.comfy.submit(prompt)
    ctx.db.execute("UPDATE jobs SET status='submitted', comfy_prompt_id=?, started_at=?, error=NULL WHERE id=?",
                   (prompt_id, now_iso(), job["id"]))


async def _collect_job(ctx: Context, job: dict) -> None:
    result = await ctx.comfy.result(job["comfy_prompt_id"])
    if not result.done:
        state = await ctx.comfy.is_pending(job["comfy_prompt_id"])
        if state == "running" and job["status"] != "running":
            ctx.db.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
        elif state is None:
            # Not queued and no history: ComfyUI restarted or lost the prompt.
            started = parse_iso(job["started_at"])
            if (utcnow() - started).total_seconds() > 60:
                _fail_job(ctx, job, "ComfyUI lost this job (was it restarted?)")
        return
    if not result.success:
        _fail_job(ctx, job, result.error or "generation failed")
        return
    if not result.outputs:
        _fail_job(ctx, job, "the workflow finished but produced no output files")
        return
    params = _job_params(job)
    for out in result.outputs:
        data = await ctx.comfy.download(out)
        try:
            ctx.media.save(user_id=job["user_id"], data=data, original_name=out.filename, source="generated",
                           job_id=job["id"], prompt=job["prompt"], width=params.get("width"),
                           height=params.get("height"))
        except MediaError as exc:
            log.warning("job %s: skipped output %s: %s", job["id"], out.filename, exc)
    if not ctx.db.one("SELECT 1 FROM media WHERE job_id=?", (job["id"],)):
        _fail_job(ctx, job, "the workflow produced no usable image or video")
        return
    ctx.db.execute("UPDATE jobs SET status='succeeded', finished_at=? WHERE id=?", (now_iso(), job["id"]))


def _fail_job(ctx: Context, job: dict, message: str) -> None:
    ctx.db.execute("UPDATE jobs SET status='failed', error=?, finished_at=? WHERE id=?",
                   (message[:1000], now_iso(), job["id"]))


async def process_jobs(ctx: Context) -> None:
    timeout = ctx.settings.job_timeout_s
    for job in ctx.db.all("SELECT * FROM jobs WHERE status IN ('queued','submitted','running') ORDER BY id"):
        age = (utcnow() - parse_iso(job["created_at"])).total_seconds()
        try:
            if age > timeout:
                _fail_job(ctx, job, f"timed out after {timeout // 60} minutes")
            elif job["status"] == "queued":
                await _submit_job(ctx, job)
            else:
                await _collect_job(ctx, job)
        except WorkflowError as exc:
            _fail_job(ctx, job, str(exc))
        except ComfyUIError as exc:
            if job["status"] == "queued" and "cannot reach" in str(exc):
                ctx.db.execute("UPDATE jobs SET error=? WHERE id=?", (f"Waiting for ComfyUI: {exc}", job["id"]))
            elif job["status"] == "queued":
                _fail_job(ctx, job, str(exc))
            else:
                log.warning("job %s: %s", job["id"], exc)


def new_seed() -> int:
    return random.randint(0, 2**48)


# --------------------------------------------------------------------------- publishing

async def publish_target(ctx: Context, post: dict, target: dict, media: dict) -> None:
    ctx.db.execute("UPDATE post_targets SET status='publishing', updated_at=? WHERE id=?", (now_iso(), target["id"]))
    try:
        account = ctx.db.one("SELECT * FROM social_accounts WHERE id=? AND user_id=?",
                             (target["account_id"], post["user_id"])) if target["account_id"] else None
        if not account:
            raise PlatformError("the social account was disconnected")
        platform = ctx.platforms[account["platform"]]
        if not platform.configured:
            raise PlatformError(f"{platform.label} is not configured on this server")
        if media["kind"] not in platform.media_kinds:
            raise PlatformError(f"{platform.label} does not accept {media['kind']} posts")
        path = ctx.media.jpeg_path(media) if (media["kind"] == "image" and platform.key == "instagram") \
            else ctx.media.path(media["stored_name"])
        mime = "image/jpeg" if path.suffix == ".jpg" else media["mime"]
        file = MediaFile(path=path, mime=mime, kind=media["kind"], size=path.stat().st_size,
                         public_url=lambda: public_media_url(ctx, media))
        token = await access_token_for(ctx, account)
        result = await platform.publish(token, account, file, post["title"], post["caption"])
        ctx.db.execute("UPDATE post_targets SET status='published', external_id=?, external_url=?, error=NULL,"
                       " updated_at=? WHERE id=?", (result.external_id, result.url, now_iso(), target["id"]))
    except (PlatformError, MediaError, ValueError, httpx.HTTPError) as exc:
        message = str(exc) or exc.__class__.__name__
        log.warning("post %s target %s failed: %s", post["id"], target["id"], message)
        ctx.db.execute("UPDATE post_targets SET status='failed', error=?, updated_at=? WHERE id=?",
                       (message[:1000], now_iso(), target["id"]))


def finalize_post_status(ctx: Context, post_id: int) -> None:
    states = [r["status"] for r in ctx.db.all("SELECT status FROM post_targets WHERE post_id=?", (post_id,))]
    if not states or any(s in ("pending", "publishing") for s in states):
        return
    status = "published" if all(s == "published" for s in states) else \
        "failed" if all(s == "failed" for s in states) else "partial"
    ctx.db.execute("UPDATE posts SET status=?, updated_at=? WHERE id=?", (status, now_iso(), post_id))


async def publish_post(ctx: Context, post_id: int) -> None:
    post = ctx.db.one("SELECT * FROM posts WHERE id=?", (post_id,))
    media = ctx.db.one("SELECT * FROM media WHERE id=?", (post["media_id"],))
    targets = ctx.db.all("SELECT * FROM post_targets WHERE post_id=? AND status='pending'", (post_id,))
    await asyncio.gather(*(publish_target(ctx, post, t, media) for t in targets))
    finalize_post_status(ctx, post_id)


async def process_due_posts(ctx: Context) -> list[asyncio.Task]:
    started = []
    for post in ctx.db.all("SELECT id FROM posts WHERE status='scheduled' AND scheduled_at <= ? ORDER BY scheduled_at",
                           (now_iso(),)):
        claimed = ctx.db.execute("UPDATE posts SET status='publishing', updated_at=? WHERE id=? AND status='scheduled'",
                                 (now_iso(), post["id"]))
        if claimed:
            task = asyncio.create_task(publish_post(ctx, post["id"]))
            ctx.tasks.add(task)
            task.add_done_callback(ctx.tasks.discard)
            started.append(task)
    return started


def recover_interrupted(ctx: Context) -> None:
    """Posts left mid-publish by a crash cannot be resumed safely; mark them failed."""
    for post in ctx.db.all("SELECT id FROM posts WHERE status='publishing'"):
        ctx.db.execute("UPDATE post_targets SET status='failed', error='interrupted by a server restart; retry to "
                       "publish again', updated_at=? WHERE post_id=? AND status IN ('pending','publishing')",
                       (now_iso(), post["id"]))
        finalize_post_status(ctx, post["id"])


async def run_worker(ctx: Context, stop: asyncio.Event) -> None:
    recover_interrupted(ctx)
    while not stop.is_set():
        for step in (process_jobs, process_due_posts):
            try:
                await step(ctx)
            except Exception:  # keep the worker alive; details go to the log
                log.exception("worker step %s failed", step.__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=ctx.settings.poll_interval_s)
        except asyncio.TimeoutError:
            pass
