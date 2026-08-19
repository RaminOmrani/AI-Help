"""کلاینت AvalAI — سازگار با OpenAI (چت، امبدینگ، اعتبار).

مستندات: https://docs.avalai.ir/en/  |  Base URL: https://api.avalai.ir/v1
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from . import config, settings


class AvalAIError(RuntimeError):
    """خطای قابل نمایش به کاربر."""


def _headers() -> dict[str, str]:
    key = settings.api_key()
    if not key:
        raise AvalAIError(
            "کلید AvalAI تنظیم نشده است. آن را از avalai.ir بگیرید و در پنل مدیریت ← "
            "تنظیمات ← «کلید و مدل‌ها» وارد کنید (یا در فایل \u200e.env\u200e پروژه)."
        )
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def describe(exc: BaseException | None) -> str:
    """پیام خوانا برای خطاهایی که گاهی متن خالی دارند (مثل تایم‌اوت)."""
    if exc is None:
        return "خطای نامشخص"
    name = type(exc).__name__
    text = str(exc).strip()
    friendly = {
        "ReadTimeout": "پاسخ سرویس در زمان مقرر نرسید (تایم‌اوت)",
        "ConnectTimeout": "اتصال به سرویس برقرار نشد (تایم‌اوت اتصال)",
        "ConnectError": "اتصال به سرویس ممکن نشد — اینترنت یا فیلترینگ را بررسی کنید",
        "ReadError": "ارتباط وسط کار قطع شد",
        "RemoteProtocolError": "سرویس ارتباط را نیمه‌کاره بست",
        "PoolTimeout": "صف درخواست‌ها پر شد",
    }.get(name)
    if friendly:
        return f"{friendly} [{name}]"
    return f"{name}: {text}" if text else name


def _friendly(status: int, body: str) -> str:
    detail = body.strip()
    try:
        parsed = json.loads(body)
        detail = (
            parsed.get("error", {}).get("message")
            if isinstance(parsed.get("error"), dict)
            else parsed.get("detail") or parsed.get("message") or body
        ) or body
    except Exception:
        pass
    detail = str(detail)[:400]
    if status in (401, 403):
        return f"کلید API معتبر نیست یا دسترسی ندارد ({status}). {detail}"
    if status == 402:
        return f"اعتبار حساب AvalAI کافی نیست. {detail}"
    if status == 429:
        return f"تعداد درخواست‌ها بیش از حد مجاز است، کمی بعد دوباره تلاش کنید. {detail}"
    if status == 404:
        return (f"مدل یا اندپوینت پیدا نشد ({status}). نام مدل را در پنل مدیریت ← "
                f"«کلید و مدل‌ها» بررسی کنید. {detail}")
    return f"خطای سرویس AvalAI ({status}): {detail}"


# ------------------------------------------------------------------
# چت
# ------------------------------------------------------------------
async def chat_stream(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.25,
    max_tokens: int = 1600,
) -> AsyncIterator[str]:
    """پاسخ مدل را به صورت توکن‌به‌توکن برمی‌گرداند."""
    payload = {
        "model": model or settings.chat_model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    url = f"{config.AVALAI_BASE_URL}/chat/completions"
    timeout = httpx.Timeout(config.REQUEST_TIMEOUT, connect=20.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=_headers(), json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise AvalAIError(_friendly(resp.status_code, body))
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    yield piece


async def chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.25,
    max_tokens: int = 1200,
) -> str:
    """پاسخ کامل (بدون استریم) — برای کارهای داخلی مثل بازنویسی لحن."""
    payload = {
        "model": model or settings.fast_model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    url = f"{config.AVALAI_BASE_URL}/chat/completions"
    async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        if resp.status_code >= 400:
            raise AvalAIError(_friendly(resp.status_code, resp.text))
        data = resp.json()
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError):
        raise AvalAIError("پاسخ نامعتبر از سرویس دریافت شد.")


# ------------------------------------------------------------------
# امبدینگ
# ------------------------------------------------------------------
async def embed(
    texts: list[str],
    *,
    model: str | None = None,
    timeout: float | None = None,
) -> list[list[float]]:
    """بردارسازی با تلاش دوباره در صورت قطعی موقتِ شبکه."""
    if not texts:
        return []

    payload = {"model": model or settings.embedding_model(), "input": texts}
    url = f"{config.AVALAI_BASE_URL}/embeddings"
    limit = timeout or config.EMBED_TIMEOUT
    last: Exception | None = None

    for attempt in range(max(config.EMBED_RETRIES, 1)):
        try:
            async with httpx.AsyncClient(timeout=limit) as client:
                resp = await client.post(url, headers=_headers(), json=payload)
            if resp.status_code >= 400:
                # خطای سرویس (کلید، مدل، اعتبار) با تلاش دوباره درست نمی‌شود
                raise AvalAIError(_friendly(resp.status_code, resp.text))
            data = resp.json()
            items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
            return [item["embedding"] for item in items]
        except AvalAIError:
            raise
        except httpx.HTTPError as exc:
            last = exc
            if attempt + 1 < config.EMBED_RETRIES:
                await asyncio.sleep(1.5 * (attempt + 1))

    raise AvalAIError(describe(last) if last else "بردارسازی ناموفق بود.")


# ------------------------------------------------------------------
# اعتبار و مدل‌ها
# ------------------------------------------------------------------
async def credit() -> dict[str, Any]:
    """مانده‌ی اعتبار حساب AvalAI."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(config.AVALAI_CREDIT_URL, headers=_headers())
        if resp.status_code >= 400:
            raise AvalAIError(_friendly(resp.status_code, resp.text))
        return resp.json()


async def list_models() -> list[str]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{config.AVALAI_BASE_URL}/models", headers=_headers())
        if resp.status_code >= 400:
            raise AvalAIError(_friendly(resp.status_code, resp.text))
        data = resp.json()
    return sorted({m.get("id", "") for m in data.get("data", []) if m.get("id")})
