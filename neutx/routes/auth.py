"""Accounts: sign up, sign in, profile, password, sessions, export, deletion."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..db import now_iso, parse_iso, utcnow
from ..deps import clear_session_cookie, create_session, current_session, current_user, get_ctx, valid_timezone
from ..security import DUMMY_HASH, hash_password, verify_password
from ..services import Context

router = APIRouter(prefix="/api/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[A-Za-z]{2,}$")
PLATFORM_KEYS = {"tiktok", "instagram", "youtube", "x"}


class SignupIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=10, max_length=256)
    name: str = Field(default="", max_length=80)
    timezone: str = Field(default="UTC", max_length=64)


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=320)
    timezone: str | None = Field(default=None, max_length=64)
    default_hashtags: str | None = Field(default=None, max_length=500)
    default_platforms: list[str] | None = None
    default_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    default_template_id: int | None = None
    clear_default_template: bool = False


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class DeleteIn(BaseModel):
    password: str = Field(max_length=256)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.match(value):
        raise HTTPException(422, "enter a valid email address")
    return value


def public_user(user: dict) -> dict:
    return {
        "id": user["id"], "email": user["email"], "name": user["name"], "timezone": user["timezone"],
        "default_hashtags": user["default_hashtags"], "default_platforms": json.loads(user["default_platforms"]),
        "default_time": user["default_time"], "default_template_id": user["default_template_id"],
        "password_changed_at": user["password_changed_at"], "created_at": user["created_at"],
    }


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, response: Response, ctx: Context = Depends(get_ctx)):
    if not ctx.settings.allow_signup:
        raise HTTPException(403, "sign-ups are disabled on this server")
    if not ctx.signup_limiter.allow(_client_ip(request)):
        raise HTTPException(429, "too many sign-ups from this address; try again later")
    email = _email(body.email)
    if ctx.db.one("SELECT 1 FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "an account with this email already exists")
    now = now_iso()
    user_id = ctx.db.execute(
        "INSERT INTO users (email, name, password_hash, timezone, password_changed_at, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (email, body.name.strip(), hash_password(body.password), valid_timezone(body.timezone), now, now),
    )
    create_session(ctx, response, user_id, request.headers.get("user-agent", ""))
    return public_user(ctx.db.one("SELECT * FROM users WHERE id=?", (user_id,)))


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, ctx: Context = Depends(get_ctx)):
    email = body.email.strip().lower()
    if not ctx.login_limiter.allow(f"{_client_ip(request)}|{email}"):
        raise HTTPException(429, "too many attempts; wait a few minutes")
    user = ctx.db.one("SELECT * FROM users WHERE email = ?", (email,))
    if not verify_password(body.password, user["password_hash"] if user else DUMMY_HASH) or not user:
        raise HTTPException(401, "incorrect email or password")
    create_session(ctx, response, user["id"], request.headers.get("user-agent", ""))
    return public_user(user)


@router.post("/logout", status_code=204)
def logout(response: Response, session: dict = Depends(current_session), ctx: Context = Depends(get_ctx)):
    ctx.db.execute("DELETE FROM sessions WHERE token_hash=?", (session["token_hash"],))
    clear_session_cookie(ctx, response)


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return public_user(user)


@router.patch("/me")
def update_me(body: ProfileIn, user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.email is not None:
        email = _email(body.email)
        if email != user["email"] and ctx.db.one("SELECT 1 FROM users WHERE email=?", (email,)):
            raise HTTPException(409, "that email is already in use")
        updates["email"] = email
    if body.timezone is not None:
        updates["timezone"] = valid_timezone(body.timezone)
    if body.default_hashtags is not None:
        updates["default_hashtags"] = body.default_hashtags.strip()
    if body.default_platforms is not None:
        if not set(body.default_platforms) <= PLATFORM_KEYS:
            raise HTTPException(422, "unknown platform in default_platforms")
        updates["default_platforms"] = json.dumps(sorted(set(body.default_platforms)))
    if body.default_time is not None:
        updates["default_time"] = body.default_time
    if body.clear_default_template:
        updates["default_template_id"] = None
    elif body.default_template_id is not None:
        if not ctx.db.one("SELECT 1 FROM templates WHERE id=? AND (user_id IS NULL OR user_id=?)",
                          (body.default_template_id, user["id"])):
            raise HTTPException(404, "template not found")
        updates["default_template_id"] = body.default_template_id
    if updates:
        cols = ", ".join(f"{k}=?" for k in updates)  # keys come from the fixed set above
        ctx.db.execute(f"UPDATE users SET {cols} WHERE id=?", (*updates.values(), user["id"]))
    return public_user(ctx.db.one("SELECT * FROM users WHERE id=?", (user["id"],)))


@router.post("/password", status_code=204)
def change_password(body: PasswordIn, session: dict = Depends(current_session), ctx: Context = Depends(get_ctx)):
    if not verify_password(body.current_password, session["password_hash"]):
        raise HTTPException(403, "current password is incorrect")
    ctx.db.execute("UPDATE users SET password_hash=?, password_changed_at=? WHERE id=?",
                   (hash_password(body.new_password), now_iso(), session["id"]))
    # Sign out every other session.
    ctx.db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (session["id"], session["token_hash"]))


@router.get("/sessions")
def sessions(session: dict = Depends(current_session), ctx: Context = Depends(get_ctx)):
    rows = ctx.db.all("SELECT token_hash, user_agent, created_at, last_seen_at, expires_at FROM sessions"
                      " WHERE user_id=? ORDER BY last_seen_at DESC", (session["id"],))
    return [{"id": r["token_hash"][:16], "user_agent": r["user_agent"], "created_at": r["created_at"],
             "last_seen_at": r["last_seen_at"], "current": r["token_hash"] == session["token_hash"]}
            for r in rows if parse_iso(r["expires_at"]) > utcnow()]


@router.delete("/sessions/{sid}", status_code=204)
def revoke_session(sid: str, session: dict = Depends(current_session), ctx: Context = Depends(get_ctx)):
    if not re.fullmatch(r"[0-9a-f]{16}", sid):
        raise HTTPException(404, "session not found")
    if session["token_hash"].startswith(sid):
        raise HTTPException(400, "use sign out to end the current session")
    if not ctx.db.execute("DELETE FROM sessions WHERE user_id=? AND substr(token_hash,1,16)=?", (session["id"], sid)):
        raise HTTPException(404, "session not found")


@router.post("/sessions/revoke-others", status_code=204)
def revoke_others(session: dict = Depends(current_session), ctx: Context = Depends(get_ctx)):
    ctx.db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (session["id"], session["token_hash"]))


@router.get("/export")
def export(user: dict = Depends(current_user), ctx: Context = Depends(get_ctx)):
    uid = user["id"]
    data = {
        "user": public_user(user),
        "templates": ctx.db.all("SELECT id, name, description, workflow, aspect, style_prompt, negative_prompt,"
                                " created_at, updated_at FROM templates WHERE user_id=?", (uid,)),
        "media": ctx.db.all("SELECT id, kind, original_name, mime, size_bytes, width, height, source, prompt,"
                            " created_at FROM media WHERE user_id=?", (uid,)),
        "posts": ctx.db.all("SELECT id, media_id, title, caption, scheduled_at, status, created_at FROM posts"
                            " WHERE user_id=?", (uid,)),
        "post_targets": ctx.db.all("SELECT t.post_id, t.platform, t.status, t.external_url, t.error FROM post_targets t"
                                   " JOIN posts p ON p.id=t.post_id WHERE p.user_id=?", (uid,)),
        "social_accounts": ctx.db.all("SELECT platform, username, created_at FROM social_accounts WHERE user_id=?", (uid,)),
        "exported_at": now_iso(),
    }
    return Response(json.dumps(data, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="neutx-export.json"'})


@router.post("/delete-account", status_code=204)
def delete_account(body: DeleteIn, response: Response, session: dict = Depends(current_session),
                   ctx: Context = Depends(get_ctx)):
    if not verify_password(body.password, session["password_hash"]):
        raise HTTPException(403, "password is incorrect")
    for row in ctx.db.all("SELECT * FROM media WHERE user_id=?", (session["id"],)):
        ctx.media.delete(row)
    ctx.db.execute("DELETE FROM users WHERE id=?", (session["id"],))
    clear_session_cookie(ctx, response)
