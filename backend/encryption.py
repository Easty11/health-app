from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from dotenv import load_dotenv
import os

load_dotenv()

# FERNET_KEY encrypts. FERNET_KEY_PREVIOUS, when set and non-empty, is a decrypt-only fallback so
# the key can be swapped with no window in which stored credentials are unreadable
# (scripts.rotate_fernet then moves the rows; docs/rotation-runbook-2026-10.md is the procedure).
# A malformed key raises at import, for the previous key exactly as for the current one.
_current: Fernet
_multi: MultiFernet
_key_count: int


def _configure(current_key: str, previous_key: str | None = None) -> None:
    global _current, _multi, _key_count
    current = Fernet(current_key.encode())
    fernets = [current]
    if previous_key:
        fernets.append(Fernet(previous_key.encode()))
    _current, _multi, _key_count = current, MultiFernet(fernets), len(fernets)


_configure(os.environ["FERNET_KEY"], os.environ.get("FERNET_KEY_PREVIOUS"))


def encrypt(plaintext: str) -> str:
    return _multi.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _multi.decrypt(token.encode()).decode()


def rotate(token: str) -> str:
    """Re-encrypt `token` under the current key (decrypts under current or previous)."""
    return _multi.rotate(token.encode()).decode()


def active_key_count() -> int:
    return _key_count


def decrypts_under_current(token: str) -> bool:
    """True when `token` decrypts under the current key alone (no fallback)."""
    try:
        _current.decrypt(token.encode())
    except InvalidToken:
        return False
    return True
