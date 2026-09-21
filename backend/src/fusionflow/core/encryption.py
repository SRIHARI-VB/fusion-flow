from cryptography.fernet import Fernet, InvalidToken

from fusionflow.config import get_settings

settings = get_settings()

# `encryption_key_version` convention: every table that stores an
# encrypted secret (e.g. connector_credentials, built in a later wave)
# should carry an `encryption_key_version` integer column alongside the
# ciphertext. Today there is exactly one key (settings.ENCRYPTION_KEY) so
# every row is version 1. When this moves to a real KMS, new secrets get
# written with an incremented version and _KEY_REGISTRY below grows a new
# entry per version so old ciphertext keeps decrypting during rotation.
CURRENT_KEY_VERSION = 1
_KEY_REGISTRY = {1: settings.ENCRYPTION_KEY}


def _fernet_for(key_version: int) -> Fernet:
    try:
        key = _KEY_REGISTRY[key_version]
    except KeyError as exc:
        raise NotImplementedError(
            f"no encryption key registered for key_version={key_version}"
        ) from exc
    return Fernet(key)


def encrypt_secret(plaintext: str, key_version: int = CURRENT_KEY_VERSION) -> bytes:
    return _fernet_for(key_version).encrypt(plaintext.encode("utf-8"))


def decrypt_secret(ciphertext: bytes, key_version: int = CURRENT_KEY_VERSION) -> str:
    try:
        return _fernet_for(key_version).decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("could not decrypt secret: invalid token or wrong key version") from exc


_PREVIEW_MASK = "*" * 6


def redact_preview(plaintext: str) -> str:
    """Return a display-safe preview: first 3 + last 4 chars, rest masked.

    The masked middle is a fixed-length run of asterisks regardless of
    `plaintext`'s length - long provider secrets (e.g. Instagram/Google
    OAuth tokens, 150+ chars) must still fit in
    `connector_credentials.redacted_preview` (VARCHAR(200), holding a
    JSON object of one preview per credential field), and the actual
    secret length isn't information worth exposing anyway.
    """
    if len(plaintext) <= 7:
        return "*" * len(plaintext)
    return f"{plaintext[:3]}{_PREVIEW_MASK}{plaintext[-4:]}"
