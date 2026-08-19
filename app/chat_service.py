"""منطق مشترک گفتگو برای هر دو دستیار (مشتری و پشتیبان)."""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

from . import avalai, db, prompts, rag

HISTORY_TURNS = 6


def get_or_create_conversation(session_id: str, audience: str) -> int:
    row = db.query_one(
        "SELECT id FROM conversations WHERE session_id = ? AND audience = ? "
        "ORDER BY id DESC LIMIT 1",
        (session_id, audience),
    )
    if row:
        return row["id"]
    return db.execute(
        "INSERT INTO conversations(session_id, audience) VALUES (?, ?)",
        (session_id, audience),
    )


def history_messages(conv_id: int) -> list[dict]:
    rows = db.query(
        "SELECT role, content FROM messages WHERE conv_id = ? ORDER BY id DESC LIMIT ?",
        (conv_id, HISTORY_TURNS),
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def answer_stream(
    question: str,
    *,
    session_id: str,
    audience: str,
    model: str | None = None,
) -> AsyncIterator[str]:
    """جریان پاسخ به صورت SSE — رویدادها: sources | delta | done | error"""
    started = time.time()
    conv_id = get_or_create_conversation(session_id, audience)
    db.execute(
        "INSERT INTO messages(conv_id, role, content) VALUES (?, 'user', ?)",
        (conv_id, question),
    )

    try:
        hits = await rag.search(question, audience=audience)
    except Exception as exc:  # noqa: BLE001
        yield _sse({"type": "error", "message": f"خطا در جستجوی مستندات: {exc}"})
        return

    sources = [h.as_source() for h in hits]
    grounded = bool(hits)
    # برای مشتری، منابع فقط به شکل عنوان کلی نمایش داده می‌شوند
    if audience == "public":
        public_sources = []
        seen = set()
        for s in sources:
            if s["title"] in seen:
                continue
            seen.add(s["title"])
            public_sources.append({"title": s["title"], "id": s["id"]})
        yield _sse({"type": "sources", "sources": public_sources, "grounded": grounded})
    else:
        yield _sse({"type": "sources", "sources": sources, "grounded": grounded})

    system = prompts.customer_system() if audience == "public" else prompts.agent_system()
    context = rag.build_context(hits)
    messages = [{"role": "system", "content": system}]
    messages.extend(history_messages(conv_id)[:-1] if conv_id else [])
    messages.append(
        {"role": "user", "content": prompts.user_turn(question, context, audience=audience)}
    )

    collected: list[str] = []
    try:
        async for piece in avalai.chat_stream(
            messages,
            model=model,
            temperature=0.2 if audience == "internal" else 0.35,
        ):
            collected.append(piece)
            yield _sse({"type": "delta", "text": piece})
    except avalai.AvalAIError as exc:
        yield _sse({"type": "error", "message": str(exc)})
        return
    except Exception as exc:  # noqa: BLE001
        yield _sse({"type": "error", "message": f"خطای غیرمنتظره: {exc}"})
        return

    answer = "".join(collected).strip()
    if not answer:
        yield _sse({"type": "error", "message": "پاسخی از مدل دریافت نشد. دوباره تلاش کنید."})
        return

    latency = int((time.time() - started) * 1000)
    message_id = db.execute(
        "INSERT INTO messages(conv_id, role, content, sources, model, latency_ms, grounded) "
        "VALUES (?, 'assistant', ?, ?, ?, ?, ?)",
        (
            conv_id,
            answer,
            json.dumps(sources, ensure_ascii=False),
            model or "",
            latency,
            1 if grounded else 0,
        ),
    )

    if not db.query_one("SELECT title FROM conversations WHERE id = ?", (conv_id,))["title"]:
        db.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (question[:80], conv_id),
        )

    yield _sse(
        {
            "type": "done",
            "message_id": message_id,
            "conversation_id": conv_id,
            "latency_ms": latency,
            "grounded": grounded,
        }
    )
