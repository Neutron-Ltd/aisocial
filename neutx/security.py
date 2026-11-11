"""Password hashing, session tokens, token encryption and signed URLs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# A precomputed hash used to keep login timing similar for unknown emails.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class Crypto:
    """Derives independent keys from NEUTX_SECRET_KEY for encryption and signing."""

    def __init__(self, secret_key: str):
        def derive(info: bytes) -> bytes:
            return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(secret_key.encode())

        self._fernet = Fernet(base64.urlsafe_b64encode(derive(b"neutx-token-encryption")))
        self._sign_key = derive(b"neutx-url-signing")

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("stored token cannot be decrypted (was NEUTX_SECRET_KEY changed?)") from exc

    def sign(self, message: str) -> str:
        return hmac.new(self._sign_key, message.encode(), hashlib.sha256).hexdigest()

    def verify(self, message: str, signature: str) -> bool:
        return hmac.compare_digest(self.sign(message), signature)


class RateLimiter:
    """In-memory sliding-window limiter (per process) for login/signup attempts."""

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True
