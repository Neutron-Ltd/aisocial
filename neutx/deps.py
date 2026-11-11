"""Shared request helpers: context, sessions, current user, time zones."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Request, Response

from .db import iso, now_iso, parse_iso, utcnow
from .security import new_token, token_hash
from .services import Context

COOKIE = "neutx_session"


def get_ctx(request: Request) -> Context:
    return request.app.state.ctx


def create_session(ctx: Context, response: Response, user_id: int, user_agent: str) -> None:
    token = new_token()
    now = utcnow()
    expires = now + timedelta(days=ctx.settings.session_days)
    ctx.db.execute(
        "INSERT INTO sessions (token_hash, user_id, user_agent, created_at, last_seen_at, expires_at)"
        " VALUES (?,?,?,?,?,?)",
        (token_hash(token), user_id, (user_agent or "")[:200], iso(now), iso(now), iso(expires)),
    )
    response.set_cookie(COOKIE, token, max_age=ctx.settings.session_days * 86400, httponly=True,
                        samesite="lax", secure=ctx.settings.cookie_secure, path="/")


def clear_session_cookie(ctx: Context, response: Response) -> None:
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=ctx.settings.cookie_secure)


def current_session(request: Request, ctx: Context = Depends(get_ctx)) -> dict:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "not signed in")
    row = ctx.db.one(
        "SELECT s.token_hash, s.last_seen_at, s.expires_at, u.* FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token_hash = ?", (token_hash(token),))
    if not row or parse_iso(row["expires_at"]) <= utcnow():
        raise HTTPException(401, "session expired")
    if (utcnow() - parse_iso(row["last_seen_at"])).total_seconds() > 300:
        ctx.db.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now_iso(), row["token_hash"]))
    return row


def current_user(session: dict = Depends(current_session)) -> dict:
    return session


def optional_user(request: Request, ctx: Context = Depends(get_ctx)) -> dict | None:
    try:
        return current_session(request, ctx)
    except HTTPException:
        return None


def user_zone(user: dict) -> ZoneInfo:
    try:
        return ZoneInfo(user.get("timezone") or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def valid_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, f"unknown time zone {name!r}")
    return name


def local_to_utc(user: dict, day: date, at: time) -> str:
    local = datetime.combine(day, at).replace(tzinfo=user_zone(user))
    return iso(local.astimezone(timezone.utc))


def utc_to_local(user: dict, value: str) -> datetime:
    return parse_iso(value).astimezone(user_zone(user))
