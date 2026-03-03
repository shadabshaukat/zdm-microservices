"""
Shared helpers to load ZEUS API Basic Auth users from .zeus.auth.env.

Rules:
- Primary location: env var ZEUS_AUTH_FILE (optional).
- Otherwise derived from ZEUS_BASE/.zeus.auth.env (ZEUS_BASE is required).
- Required keys: ZEUS_API_USER_<N> and ZEUS_API_USER_<N>_PASSWORD (N is any token).
- Passwords are not logged or printed.
"""

from pathlib import Path
from typing import Dict, Tuple
import os
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthConfigError(RuntimeError):
    """Raised when the auth file is missing or malformed."""


def _auth_file_path() -> Path:
    env_path = os.getenv("ZEUS_AUTH_FILE")
    if env_path:
        path = Path(env_path).expanduser()
    else:
        base = os.getenv("ZEUS_BASE")
        if not base:
            raise AuthConfigError("ZEUS_BASE must be set when ZEUS_AUTH_FILE is not provided.")
        path = Path(base) / ".zeus.auth.env"
    if not path.exists():
        raise AuthConfigError(f"ZEUS auth file not found at {path}")
    return path


def _load_kv(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def load_users_plain() -> Dict[str, str]:
    """Return {user: password} from the auth file or raise AuthConfigError."""
    path = _auth_file_path()
    data = _load_kv(path)
    users: Dict[str, str] = {}
    for key, user in data.items():
        if not key.startswith("ZEUS_API_USER_"):
            continue
        suffix = key[len("ZEUS_API_USER_") :]
        pwd_key = f"ZEUS_API_USER_{suffix}_PASSWORD"
        password = data.get(pwd_key)
        if user and password:
            users[user] = password
    if not users:
        raise AuthConfigError(f"No ZEUS_API_USER_* entries found in {path}")
    return users


def load_users_hashed() -> Dict[str, str]:
    """Return {user: bcrypt_hash}."""
    return {u: pwd_context.hash(p) for u, p in load_users_plain().items()}


def first_user_defaults() -> Tuple[str, str]:
    """Return (user, password) for the first entry, or ('','') on failure."""
    try:
        users = load_users_plain()
        user, pwd = next(iter(users.items()))
        return user, pwd
    except Exception:
        return "", ""
