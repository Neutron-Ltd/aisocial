"""Workflows, templates, media library and generation jobs."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..db import dumps, now_iso
from ..deps import current_user, get_ctx
from ..media import MediaError, clean_name
from ..services import Context, new_seed
from ..workflows import ASPECTS, QUALITIES, WorkflowError

router = APIRouter(prefix="/api", tags=["content"])
Aspect = Literal["9:16", "1:1", "16:9"]


# --------------------------------------------------------------------------- workflows & templates

@router.get("/workflows")
def list_workflows(user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    return [w.public() for w in ctx.workflows.list()]


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    workflow: str = Field(max_length=64)
    aspect: Aspect = "9:16"
    style_prompt: str = Field(default="", max_length=2000)
    negative_prompt: str = Field(default="", max_length=2000)


def template_out(ctx: Context, row: dict) -> dict:
    try:
        wf = ctx.workflows.get(row["workflow"]).public()
    except WorkflowError:
        wf = None
    return {**{k: row[k] for k in ("id", "name", "description", "workflow", "aspect", "style_prompt",
                                   "negative_prompt", "created_at", "updated_at")},
            "system": row["user_id"] is None, "workflow_info": wf}


def _own_template(ctx: Context, user: dict, template_id: int, writable: bool = False) -> dict:
    row = ctx.db.one("SELECT * FROM templates WHERE id=?", (template_id,))
    if not row or (row["user_id"] not in (None, user["id"])):
        raise HTTPException(404, "template not found")
    if writable and row["user_id"] is None:
        raise HTTPException(403, "system templates cannot be changed; save a copy instead")
    return row


def _validate_template(ctx: Context, body: TemplateIn) -> None:
    try:
        wf = ctx.workflows.get(body.workflow)
    except WorkflowError as exc:
        raise HTTPException(422, str(exc))
    if body.aspect not in wf.public()["aspects"]:
        raise HTTPException(422, f"{wf.public()['name']} does not support {body.aspect}")


@router.get("/templates")
def list_templates(user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    rows = ctx.db.all("SELECT * FROM templates WHERE user_id IS NULL OR user_id=? ORDER BY user_id IS NOT NULL, id",
                      (user["id"],))
    return [template_out(ctx, r) for r in rows]


@router.get("/templates/{template_id}")
def get_template(template_id: int, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    return template_out(ctx, _own_template(ctx, user, template_id))


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    _validate_template(ctx, body)
    if ctx.db.one("SELECT COUNT(*) AS n FROM templates WHERE user_id=?", (user["id"],))["n"] >= 200:
        raise HTTPException(409, "template limit reached")
    now = now_iso()
    tid = ctx.db.execute(
        "INSERT INTO templates (user_id, name, description, workflow, aspect, style_prompt, negative_prompt,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (user["id"], body.name.strip(), body.description.strip(), body.workflow, body.aspect,
         body.style_prompt.strip(), body.negative_prompt.strip(), now, now))
    return template_out(ctx, ctx.db.one("SELECT * FROM templates WHERE id=?", (tid,)))


@router.put("/templates/{template_id}")
def update_template(template_id: int, body: TemplateIn, user: dict = Depends(current_user),
                    ctx: Context = Depends(get_ctx)):
    _own_template(ctx, user, template_id, writable=True)
    _validate_template(ctx, body)
    ctx.db.execute(
        "UPDATE templates SET name=?, description=?, workflow=?, aspect=?, style_prompt=?, negative_prompt=?,"
        " updated_at=? WHERE id=? AND user_id=?",
        (body.name.strip(), body.description.strip(), body.workflow, body.aspect, body.style_prompt.strip(),
         body.negative_prompt.strip(), now_iso(), template_id, user["id"]))
    return template_out(ctx, ctx.db.one("SELECT * FROM templates WHERE id=?", (template_id,)))


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: int, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    _own_template(ctx, user, template_id, writable=True)
    ctx.db.execute("DELETE FROM templates WHERE id=? AND user_id=?", (template_id, user["id"]))
    ctx.db.execute("UPDATE users SET default_template_id=NULL WHERE id=? AND default_template_id=?",
                   (user["id"], template_id))


# --------------------------------------------------------------------------- media

def media_out(row: dict, post_count: int | None = None) -> dict:
    out = {k: row[k] for k in ("id", "kind", "original_name", "mime", "size_bytes", "width", "height", "source",
                               "job_id", "prompt", "created_at")}
    out["url"] = f"/api/media/{row['id']}/file"
    if post_count is not None:
        out["post_count"] = post_count
    return out


def _own_media(ctx: Context, user: dict, media_id: int) -> dict:
    row = ctx.db.one("SELECT * FROM media WHERE id=? AND user_id=?", (media_id, user["id"]))
    if not row:
        raise HTTPException(404, "media not found")
    return row


@router.get("/media")
def list_media(kind: Literal["all", "image", "video"] = "all", q: str = Query("", max_length=100),
               sort: Literal["recent", "oldest", "largest"] = "recent", limit: int = Query(24, ge=1, le=100),
               offset: int = Query(0, ge=0), user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    where, params = ["m.user_id=?"], [user["id"]]
    if kind != "all":
        where.append("m.kind=?")
        params.append(kind)
    if q.strip():
        where.append("(m.original_name LIKE ? ESCAPE '\\' OR m.prompt LIKE ? ESCAPE '\\')")
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params += [like, like]
    order = {"recent": "m.id DESC", "oldest": "m.id ASC", "largest": "m.size_bytes DESC"}[sort]
    sql_where = " AND ".join(where)
    rows = ctx.db.all(
        f"SELECT m.*, (SELECT COUNT(*) FROM posts p WHERE p.media_id=m.id AND p.status<>'cancelled') AS post_count"
        f" FROM media m WHERE {sql_where} ORDER BY {order} LIMIT ? OFFSET ?", (*params, limit, offset))
    total = ctx.db.one(f"SELECT COUNT(*) AS n FROM media m WHERE {sql_where}", tuple(params))["n"]
    stats = ctx.db.all("SELECT kind, COUNT(*) AS n, COALESCE(SUM(size_bytes),0) AS bytes FROM media WHERE user_id=?"
                       " GROUP BY kind", (user["id"],))
    week = ctx.db.one("SELECT COUNT(*) AS n FROM media WHERE user_id=? AND created_at >= datetime('now','-7 days')",
                      (user["id"],))["n"]
    by_kind = {s["kind"]: s for s in stats}
    return {
        "items": [media_out(r, r["post_count"]) for r in rows], "total": total,
        "max_upload_mb": ctx.settings.max_upload_mb,
        "stats": {
            "count": sum(s["n"] for s in stats), "bytes": sum(s["bytes"] for s in stats), "added_this_week": week,
            "videos": by_kind.get("video", {"n": 0, "bytes": 0}), "images": by_kind.get("image", {"n": 0, "bytes": 0}),
        },
    }


@router.post("/media", status_code=201)
async def upload_media(files: list[UploadFile] = File(...), user: dict = Depends(current_user),
                       ctx: Context = Depends(get_ctx)):
    if len(files) > 20:
        raise HTTPException(413, "upload at most 20 files at a time")
    limit = ctx.settings.max_upload_mb * 1024 * 1024
    saved, errors = [], []
    for f in files:
        name = clean_name(f.filename or "", "upload")
        data = await f.read(limit + 1)
        if len(data) > limit:
            errors.append(f"{name}: larger than {ctx.settings.max_upload_mb} MB")
            continue
        try:
            saved.append(media_out(ctx.media.save(user_id=user["id"], data=data, original_name=name,
                                                  source="upload"), 0))
        except MediaError as exc:
            errors.append(f"{name}: {exc}")
    if not saved and errors:
        raise HTTPException(422, "; ".join(errors))
    return {"items": saved, "errors": errors}


@router.get("/media/{media_id}")
def get_media(media_id: int, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    return media_out(_own_media(ctx, user, media_id))


@router.get("/media/{media_id}/file")
def media_file(media_id: int, download: bool = False, user: dict = Depends(current_user),
               ctx: Context = Depends(get_ctx)):
    row = _own_media(ctx, user, media_id)
    return FileResponse(ctx.media.path(row["stored_name"]), media_type=row["mime"], filename=row["original_name"],
                        content_disposition_type="attachment" if download else "inline",
                        headers={"Cache-Control": "private, max-age=3600"})


class BulkIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


def _delete_media(ctx: Context, row: dict) -> None:
    if ctx.db.one("SELECT 1 FROM posts WHERE media_id=? AND status IN ('scheduled','publishing')", (row["id"],)):
        raise HTTPException(409, f"{row['original_name']} is used by a scheduled post; cancel the post first")
    ctx.db.execute("DELETE FROM media WHERE id=?", (row["id"],))
    ctx.media.delete(row)


@router.delete("/media/{media_id}", status_code=204)
def delete_media(media_id: int, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    _delete_media(ctx, _own_media(ctx, user, media_id))


@router.post("/media/bulk-delete")
def bulk_delete(body: BulkIds, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    deleted, errors = 0, []
    for mid in body.ids:
        row = ctx.db.one("SELECT * FROM media WHERE id=? AND user_id=?", (mid, user["id"]))
        if not row:
            continue
        try:
            _delete_media(ctx, row)
            deleted += 1
        except HTTPException as exc:
            errors.append(exc.detail)
    return {"deleted": deleted, "errors": errors}


# --------------------------------------------------------------------------- generation jobs

class JobIn(BaseModel):
    template_id: int
    prompt: str = Field(min_length=1, max_length=2000)
    quality: Literal["draft", "standard"] = "standard"
    length: Literal["short", "standard", "long"] | None = None
    aspect: Aspect | None = None
    image_media_id: int | None = None


def job_out(ctx: Context, job: dict) -> dict:
    params = json.loads(job["params"])
    outputs = ctx.db.all("SELECT * FROM media WHERE job_id=? ORDER BY id", (job["id"],))
    return {
        "id": job["id"], "status": job["status"], "error": job["error"], "prompt": job["prompt"],
        "template_id": job["template_id"], "workflow": job["workflow"], "params": params,
        "created_at": job["created_at"], "started_at": job["started_at"], "finished_at": job["finished_at"],
        "outputs": [media_out(m) for m in outputs],
    }


@router.post("/jobs", status_code=201)
def create_job(body: JobIn, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    tpl = _own_template(ctx, user, body.template_id)
    try:
        wf = ctx.workflows.get(tpl["workflow"])
    except WorkflowError as exc:
        raise HTTPException(422, str(exc))
    aspect = body.aspect or tpl["aspect"]
    if aspect not in ASPECTS or aspect not in wf.meta.get("sizes", {}):
        raise HTTPException(422, f"{wf.public()['name']} does not support {aspect}")
    if body.quality not in QUALITIES or body.quality not in wf.meta.get("quality", {}):
        raise HTTPException(422, "unsupported quality")
    if body.image_media_id is not None:
        img = _own_media(ctx, user, body.image_media_id)
        if img["kind"] != "image":
            raise HTTPException(422, "the hero image must be an image")
        if wf.image_input == "none":
            raise HTTPException(422, f"{wf.public()['name']} does not use a hero image")
    elif wf.image_input == "required":
        raise HTTPException(422, f"{wf.public()['name']} needs a hero image")
    active = ctx.db.one("SELECT COUNT(*) AS n FROM jobs WHERE user_id=? AND status IN ('queued','submitted','running')",
                        (user["id"],))["n"]
    if active >= 5:
        raise HTTPException(429, "you already have 5 generations in progress")
    prompt = body.prompt.strip()
    if tpl["style_prompt"]:
        prompt = f"{prompt}, {tpl['style_prompt']}"
    width, height = wf.meta["sizes"][aspect]
    params = {"aspect": aspect, "quality": body.quality, "length": body.length if wf.meta.get("lengths") else None,
              "seed": new_seed(), "negative_prompt": tpl["negative_prompt"], "width": width, "height": height,
              "kind": wf.kind, "template_name": tpl["name"], "engine": wf.meta.get("engine", "")}
    job_id = ctx.db.execute(
        "INSERT INTO jobs (user_id, template_id, workflow, status, prompt, params, input_media_id, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (user["id"], tpl["id"], tpl["workflow"], "queued", prompt, dumps(params), body.image_media_id, now_iso()))
    return job_out(ctx, ctx.db.one("SELECT * FROM jobs WHERE id=?", (job_id,)))


@router.get("/jobs")
def list_jobs(active: bool = False, limit: int = Query(20, ge=1, le=100), user: dict = Depends(current_user),
              ctx: Context = Depends(get_ctx)):
    sql = "SELECT * FROM jobs WHERE user_id=?"
    if active:
        sql += " AND status IN ('queued','submitted','running')"
    rows = ctx.db.all(sql + " ORDER BY id DESC LIMIT ?", (user["id"], limit))
    return [job_out(ctx, r) for r in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    job = ctx.db.one("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"]))
    if not job:
        raise HTTPException(404, "job not found")
    return job_out(ctx, job)
