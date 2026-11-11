"""Social platforms: OAuth connections, accounts, posts and scheduling."""

from __future__ import annotations

import logging
from datetime import date as Date, time as Time, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..db import iso, now_iso, parse_iso, utcnow
from ..deps import current_user, get_ctx, local_to_utc, optional_user, utc_to_local
from ..platforms import PlatformError
from ..security import new_token, pkce_pair, token_hash
from ..services import Context, save_account

log = logging.getLogger("neutx")
router = APIRouter(prefix="/api", tags=["social"])
RETURN_PAGES = {"connections.html", "auth.html"}


def _platform(ctx: Context, key: str):
    platform = ctx.platforms.get(key)
    if not platform:
        raise HTTPException(404, "unknown platform")
    return platform


@router.get("/platforms")
def platforms(user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    out = []
    for p in ctx.platforms.values():
        info = p.info()
        if p.key == "instagram" and not ctx.settings.public_is_https:
            info["warning"] = "Instagram needs PUBLIC_BASE_URL to be a public https URL to fetch media from."
        out.append(info)
    return out


# --------------------------------------------------------------------------- accounts & OAuth

def account_out(row: dict) -> dict:
    return {"id": row["id"], "platform": row["platform"], "username": row["username"], "external_id": row["external_id"],
            "expires_at": row["expires_at"], "refresh_expires_at": row["refresh_expires_at"],
            "has_refresh_token": bool(row["refresh_token_enc"]), "created_at": row["created_at"],
            "updated_at": row["updated_at"]}


@router.get("/accounts")
def list_accounts(user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    rows = ctx.db.all("SELECT a.*, (SELECT COUNT(*) FROM post_targets t WHERE t.account_id=a.id AND"
                      " t.status='published') AS published FROM social_accounts a WHERE a.user_id=? ORDER BY a.id",
                      (user["id"],))
    return [{**account_out(r), "published_count": r["published"]} for r in rows]


@router.delete("/accounts/{account_id}", status_code=204)
def disconnect(account_id: int, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    if not ctx.db.execute("DELETE FROM social_accounts WHERE id=? AND user_id=?", (account_id, user["id"])):
        raise HTTPException(404, "account not found")


class StartIn(BaseModel):
    return_to: str = "connections.html"


@router.post("/oauth/{platform_key}/start")
def oauth_start(platform_key: str, body: StartIn, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    platform = _platform(ctx, platform_key)
    if not platform.configured:
        raise HTTPException(409, f"{platform.label} is not configured on this server (set its client id and secret)")
    state = new_token()
    verifier, challenge = pkce_pair()
    ctx.db.execute("DELETE FROM oauth_states WHERE expires_at < ?", (now_iso(),))
    ctx.db.execute(
        "INSERT INTO oauth_states (state_hash, user_id, platform, code_verifier, return_to, expires_at)"
        " VALUES (?,?,?,?,?,?)",
        (token_hash(state), user["id"], platform.key, verifier,
         body.return_to if body.return_to in RETURN_PAGES else "connections.html",
         iso(utcnow() + timedelta(minutes=10))))
    return {"url": platform.authorize_url(state, challenge)}


@router.get("/oauth/{platform_key}/callback")
async def oauth_callback(platform_key: str, state: str = "", code: str = "", error: str = "",
                         error_description: str = "", user: dict | None = Depends(optional_user),
                         ctx: Context = Depends(get_ctx)):
    if user is None:
        return RedirectResponse("/auth.html?" + urlencode({"error": "Sign in, then connect the account again."}),
                                status_code=303)
    platform = _platform(ctx, platform_key)
    row = ctx.db.one("SELECT * FROM oauth_states WHERE state_hash=?", (token_hash(state),)) if state else None
    if row:
        ctx.db.execute("DELETE FROM oauth_states WHERE state_hash=?", (row["state_hash"],))
    page = row["return_to"] if row else "connections.html"

    def back(**params) -> RedirectResponse:
        return RedirectResponse(f"/{page}?{urlencode(params)}", status_code=303)

    if not row or row["user_id"] != user["id"] or row["platform"] != platform.key \
            or parse_iso(row["expires_at"]) < utcnow():
        return back(error="The connection request expired or was not started here. Please try again.")
    if error or not code:
        return back(error=f"{platform.label} did not authorize the connection: {error_description or error or 'no code'}")
    try:
        tokens, profile = await platform.exchange_code(code, row["code_verifier"])
    except PlatformError as exc:
        return back(error=str(exc))
    except Exception:
        log.exception("OAuth exchange with %s failed", platform.key)
        return back(error=f"Could not complete the {platform.label} connection.")
    save_account(ctx, user["id"], platform.key, tokens, profile)
    return back(connected=platform.key)


# --------------------------------------------------------------------------- posts

class PostIn(BaseModel):
    media_id: int
    account_ids: list[int] = Field(min_length=1, max_length=10)
    caption: str = Field(default="", max_length=5000)
    title: str = Field(default="", max_length=100)
    date: Date | None = None
    time: Time | None = None
    publish_now: bool = False


class PostPatch(BaseModel):
    caption: str | None = Field(default=None, max_length=5000)
    title: str | None = Field(default=None, max_length=100)
    date: Date | None = None
    time: Time | None = None


def post_out(ctx: Context, user: dict, post: dict) -> dict:
    targets = ctx.db.all("SELECT t.*, a.username FROM post_targets t LEFT JOIN social_accounts a ON a.id=t.account_id"
                         " WHERE t.post_id=? ORDER BY t.id", (post["id"],))
    media = ctx.db.one("SELECT * FROM media WHERE id=?", (post["media_id"],))
    local = utc_to_local(user, post["scheduled_at"])
    return {
        "id": post["id"], "title": post["title"], "caption": post["caption"], "status": post["status"],
        "scheduled_at": post["scheduled_at"], "local_date": local.date().isoformat(),
        "local_time": local.strftime("%H:%M"), "created_at": post["created_at"],
        "media": {"id": media["id"], "kind": media["kind"], "url": f"/api/media/{media['id']}/file",
                  "original_name": media["original_name"]} if media else None,
        "targets": [{"id": t["id"], "platform": t["platform"], "account_id": t["account_id"],
                     "username": t["username"], "status": t["status"], "url": t["external_url"],
                     "error": t["error"]} for t in targets],
    }


def _own_post(ctx: Context, user: dict, post_id: int) -> dict:
    post = ctx.db.one("SELECT * FROM posts WHERE id=? AND user_id=?", (post_id, user["id"]))
    if not post:
        raise HTTPException(404, "post not found")
    return post


@router.get("/posts")
def list_posts(start: Date | None = Query(None, alias="from"), end: Date | None = Query(None, alias="to"),
               status: str | None = Query(None, pattern=r"^(upcoming|scheduled|published|failed|partial|all)$"),
               limit: int = Query(200, ge=1, le=500), user: dict = Depends(current_user),
               ctx: Context = Depends(get_ctx)):
    where, params = ["user_id=?", "status<>'cancelled'"], [user["id"]]
    if start:
        where.append("scheduled_at >= ?")
        params.append(local_to_utc(user, start, Time(0, 0)))
    if end:
        where.append("scheduled_at < ?")
        params.append(local_to_utc(user, end + timedelta(days=1), Time(0, 0)))
    if status == "upcoming":
        where.append("status IN ('scheduled','publishing') AND scheduled_at >= ?")
        params.append(iso(utcnow() - timedelta(hours=1)))
    elif status and status != "all":
        where.append("status=?")
        params.append(status)
    rows = ctx.db.all(f"SELECT * FROM posts WHERE {' AND '.join(where)} ORDER BY scheduled_at LIMIT ?",
                      (*params, limit))
    return [post_out(ctx, user, r) for r in rows]


@router.post("/posts", status_code=201)
def create_post(body: PostIn, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    media = ctx.db.one("SELECT * FROM media WHERE id=? AND user_id=?", (body.media_id, user["id"]))
    if not media:
        raise HTTPException(404, "media not found")
    accounts = []
    for aid in dict.fromkeys(body.account_ids):
        acc = ctx.db.one("SELECT * FROM social_accounts WHERE id=? AND user_id=?", (aid, user["id"]))
        if not acc:
            raise HTTPException(404, "social account not found")
        platform = ctx.platforms[acc["platform"]]
        if media["kind"] not in platform.media_kinds:
            raise HTTPException(422, f"{platform.label} does not accept {media['kind']} posts")
        accounts.append(acc)
    if body.publish_now:
        scheduled = now_iso()
    else:
        if not body.date or not body.time:
            raise HTTPException(422, "pick a publish date and time, or publish now")
        scheduled = local_to_utc(user, body.date, body.time)
        if parse_iso(scheduled) < utcnow() - timedelta(minutes=1):
            raise HTTPException(422, "the publish time is in the past")
    now = now_iso()
    post_id = ctx.db.execute(
        "INSERT INTO posts (user_id, media_id, title, caption, scheduled_at, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,'scheduled',?,?)",
        (user["id"], media["id"], body.title.strip(), body.caption.strip(), scheduled, now, now))
    for acc in accounts:
        ctx.db.execute("INSERT INTO post_targets (post_id, account_id, platform, status, updated_at)"
                       " VALUES (?,?,?,'pending',?)", (post_id, acc["id"], acc["platform"], now))
    return post_out(ctx, user, ctx.db.one("SELECT * FROM posts WHERE id=?", (post_id,)))


@router.get("/posts/{post_id}")
def get_post(post_id: int, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    return post_out(ctx, user, _own_post(ctx, user, post_id))


@router.patch("/posts/{post_id}")
def update_post(post_id: int, body: PostPatch, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    post = _own_post(ctx, user, post_id)
    if post["status"] != "scheduled":
        raise HTTPException(409, "only scheduled posts can be edited")
    current = utc_to_local(user, post["scheduled_at"])
    scheduled = post["scheduled_at"]
    if body.date or body.time:
        scheduled = local_to_utc(user, body.date or current.date(), body.time or current.time().replace(second=0))
        if parse_iso(scheduled) < utcnow() - timedelta(minutes=1):
            raise HTTPException(422, "the publish time is in the past")
    ctx.db.execute("UPDATE posts SET caption=?, title=?, scheduled_at=?, updated_at=? WHERE id=? AND status='scheduled'",
                   (body.caption.strip() if body.caption is not None else post["caption"],
                    body.title.strip() if body.title is not None else post["title"],
                    scheduled, now_iso(), post_id))
    return post_out(ctx, user, ctx.db.one("SELECT * FROM posts WHERE id=?", (post_id,)))


@router.delete("/posts/{post_id}", status_code=204)
def cancel_post(post_id: int, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    post = _own_post(ctx, user, post_id)
    if post["status"] == "publishing":
        raise HTTPException(409, "this post is being published right now")
    if post["status"] == "scheduled":
        ctx.db.execute("UPDATE posts SET status='cancelled', updated_at=? WHERE id=?", (now_iso(), post_id))
    else:
        ctx.db.execute("DELETE FROM posts WHERE id=?", (post_id,))


@router.post("/posts/{post_id}/retry")
def retry_post(post_id: int, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    post = _own_post(ctx, user, post_id)
    if post["status"] not in ("failed", "partial"):
        raise HTTPException(409, "only failed posts can be retried")
    now = now_iso()
    ctx.db.execute("UPDATE post_targets SET status='pending', error=NULL, updated_at=? WHERE post_id=? AND status='failed'",
                   (now, post_id))
    ctx.db.execute("UPDATE posts SET status='scheduled', scheduled_at=?, updated_at=? WHERE id=?", (now, now, post_id))
    return post_out(ctx, user, ctx.db.one("SELECT * FROM posts WHERE id=?", (post_id,)))
