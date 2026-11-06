"""Server-side secrets: hashing tokens, encrypting the SII token at rest, refresh tokens."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Used only when SESSION_SECRET is not configured (local development).
_EPHEMERAL_SECRET = secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """sha256 hex digest: what we store instead of a token, so a DB leak exposes nothing usable."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    """Opaque, unguessable value for the HttpOnly refresh cookie (256 bits)."""
    return secrets.token_urlsafe(32)


class TokenCipher:
    """Symmetric encryption (Fernet: AES-128-CBC + HMAC-SHA256) keyed from the server secret."""

    def __init__(self, secret: str) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str | None:
        """None when the value was encrypted with another secret or was tampered with."""
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            return None


@lru_cache
def get_cipher(secret: str) -> TokenCipher:
    if not secret:
        logger.warning("SESSION_SECRET is not set: using a per-process secret (sessions won't survive restarts).")
        return TokenCipher(_EPHEMERAL_SECRET)
    return TokenCipher(secret)
