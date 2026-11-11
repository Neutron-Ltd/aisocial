"""Runtime configuration, read from environment variables (and an optional .env).

Nothing secret has a default: NEUTX_SECRET_KEY must be set, and each social
platform is only enabled when both its client id and secret are present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

ROOT_DIR = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines. Real environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int, minimum: int = 1) -> int:
    value = os.environ.get(name, "")
    if not value:
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if number < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return number


def _http_url(name: str, default: str) -> str:
    value = os.environ.get(name) or default
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError(f"{name} must be an http(s) URL, got {value!r}")
    if parts.username or parts.password:
        raise ConfigError(f"{name} must not contain credentials")
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def _path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    path = Path(value).expanduser() if value else default
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


@dataclass(frozen=True)
class PlatformCredentials:
    client_id: str
    client_secret: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


@dataclass(frozen=True)
class Settings:
    secret_key: str
    public_base_url: str
    host: str
    port: int
    data_dir: Path
    workflows_dir: Path
    webui_dir: Path
    comfyui_url: str
    comfyui_timeout_s: int
    job_timeout_s: int
    max_upload_mb: int
    allow_signup: bool
    cookie_secure: bool
    session_days: int
    worker_enabled: bool
    poll_interval_s: float
    tiktok: PlatformCredentials
    tiktok_privacy_level: str
    instagram: PlatformCredentials
    youtube: PlatformCredentials
    youtube_privacy_status: str
    x: PlatformCredentials
    extra: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "neutx.sqlite3"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def public_is_https(self) -> bool:
        return self.public_base_url.startswith("https://")


def load_settings(env_file: Path | None = ROOT_DIR / ".env") -> Settings:
    if env_file is not None:
        load_dotenv(env_file)

    secret = os.environ.get("NEUTX_SECRET_KEY", "")
    if len(secret) < 32:
        raise ConfigError(
            "NEUTX_SECRET_KEY must be set to a random string of at least 32 characters "
            "(generate one with: python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
        )

    public_base_url = _http_url("PUBLIC_BASE_URL", "http://127.0.0.1:8080")

    tiktok_privacy = os.environ.get("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")
    if tiktok_privacy not in ("SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"):
        raise ConfigError("TIKTOK_PRIVACY_LEVEL is not a valid TikTok privacy level")
    yt_privacy = os.environ.get("YOUTUBE_PRIVACY_STATUS", "private")
    if yt_privacy not in ("private", "unlisted", "public"):
        raise ConfigError("YOUTUBE_PRIVACY_STATUS must be private, unlisted or public")

    def creds(prefix: str) -> PlatformCredentials:
        return PlatformCredentials(
            os.environ.get(f"{prefix}_CLIENT_ID", ""), os.environ.get(f"{prefix}_CLIENT_SECRET", "")
        )

    return Settings(
        secret_key=secret,
        public_base_url=public_base_url,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=_int("PORT", 8080),
        data_dir=_path("DATA_DIR", ROOT_DIR / "data"),
        workflows_dir=_path("WORKFLOWS_DIR", ROOT_DIR / "workflows"),
        webui_dir=ROOT_DIR / "WebUI",
        comfyui_url=_http_url("COMFYUI_URL", "http://127.0.0.1:8188"),
        comfyui_timeout_s=_int("COMFYUI_TIMEOUT", 30),
        job_timeout_s=_int("JOB_TIMEOUT", 3600),
        max_upload_mb=_int("MAX_UPLOAD_MB", 200),
        allow_signup=_bool("ALLOW_SIGNUP", True),
        cookie_secure=_bool("COOKIE_SECURE", public_base_url.startswith("https://")),
        session_days=_int("SESSION_DAYS", 14),
        worker_enabled=_bool("WORKER_ENABLED", True),
        poll_interval_s=float(os.environ.get("POLL_INTERVAL", "2") or 2),
        tiktok=creds("TIKTOK"),
        tiktok_privacy_level=tiktok_privacy,
        instagram=creds("INSTAGRAM"),
        youtube=creds("YOUTUBE"),
        youtube_privacy_status=yt_privacy,
        x=creds("X"),
    )
