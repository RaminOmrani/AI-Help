"""احراز هویت ساده و بدون وابستگی: توکن امضاشده با HMAC."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Header, HTTPException

from . import config

ROLE_PASSWORDS = {
    "admin": lambda: config.ADMIN_PASSWORD,
    "agent": lambda: config.AGENT_PASSWORD,
}


def _sign(payload: bytes) -> str:
    digest = hmac.new(config.SECRET_KEY.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(role: str) -> str:
    payload = json.dumps(
        {"role": role, "exp": int(time.time()) + config.SESSION_HOURS * 3600}
    ).encode()
    body = _b64(payload)
    return f"{body}.{_sign(payload)}"


def verify_token(token: str) -> str | None:
    """نقش کاربر را برمی‌گرداند یا None."""
    try:
        body, signature = token.split(".", 1)
        payload = _unb64(body)
    except Exception:  # noqa: BLE001
        return None
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("role")


def login(role: str, password: str) -> str:
    getter = ROLE_PASSWORDS.get(role)
    if not getter:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است.")
    expected = getter()
    if not expected or not hmac.compare_digest(password or "", expected):
        raise HTTPException(status_code=401, detail="رمز عبور اشتباه است.")
    return create_token(role)


def _extract(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="ابتدا وارد شوید.")
    return authorization.removeprefix("Bearer ").strip()


async def require_admin(authorization: str | None = Header(default=None)) -> str:
    role = verify_token(_extract(authorization))
    if role != "admin":
        raise HTTPException(status_code=403, detail="دسترسی مدیر لازم است.")
    return role


async def require_staff(authorization: str | None = Header(default=None)) -> str:
    """پشتیبان یا مدیر."""
    role = verify_token(_extract(authorization))
    if role not in {"admin", "agent"}:
        raise HTTPException(status_code=403, detail="دسترسی کارشناس پشتیبانی لازم است.")
    return role
