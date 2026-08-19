"""دستیار پشتیبانی هوشمند — سرور FastAPI (API + سرو کردن رابط کاربری)."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import unicodedata
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import avalai, chat_service, config, db, diagnostics, ingest, prompts, rag, security, settings

app = FastAPI(title="Support AI — AvalAI", version="3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIENCES = {"public", "internal", "both"}


@app.on_event("startup")
async def startup() -> None:
    db.init_db()


# ==================================================================
# مدل‌های ورودی
# ==================================================================
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="anonymous", max_length=64)
    client_id: str = Field(default="", max_length=64)
    length: str = Field(default="normal", pattern="^(short|normal|detailed)$")
    model: str | None = None


class FeedbackIn(BaseModel):
    message_id: int
    value: int  # 1 یا -1


class TicketIn(BaseModel):
    name: str = ""
    contact: str = ""
    subject: str = ""
    body: str = ""
    session_id: str = ""


class LoginIn(BaseModel):
    role: str
    password: str


class RewriteIn(BaseModel):
    text: str


class DocPatchIn(BaseModel):
    title: str | None = None
    audience: str | None = None
    category: str | None = None
    ai_repair: bool | None = None


class SettingsIn(BaseModel):
    values: dict[str, str]


class AISettingsIn(BaseModel):
    avalai_api_key: str | None = None
    chat_model: str | None = None
    fast_model: str | None = None
    vision_model: str | None = None
    embedding_model: str | None = None
    vision_enabled: bool | None = None


# ==================================================================
# عمومی (مشتری)
# ==================================================================
def _suggestions(key: str) -> list[str]:
    return db.get_json_setting(key, [])


@app.get("/api/bootstrap")
async def bootstrap():
    welcome = db.get_setting("welcome_customer", "").format(
        assistant=config.ASSISTANT_NAME, product=config.BRAND_PRODUCT
    )
    return {
        "brand": config.BRAND_NAME,
        "product": config.BRAND_PRODUCT,
        "assistant": config.ASSISTANT_NAME,
        "support_phone": config.SUPPORT_PHONE,
        "support_hours": config.SUPPORT_HOURS,
        "welcome": welcome,
        "suggestions": _suggestions("customer_suggestions"),
        "ready": rag.stats()["ready"] > 0,
    }


@app.post("/api/chat")
async def customer_chat(payload: ChatIn):
    return StreamingResponse(
        chat_service.answer_stream(
            payload.message.strip(),
            session_id=payload.session_id,
            audience="public",
            client_id=payload.client_id,
            length=payload.length,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _delete_conversation(session_id: str, client_id: str, audience: str) -> bool:
    row = db.query_one(
        "SELECT id FROM conversations WHERE session_id = ? AND client_id = ? AND audience = ?",
        (session_id, client_id, audience),
    )
    if not row:
        return False
    db.execute("DELETE FROM messages WHERE conv_id = ?", (row["id"],))
    db.execute("DELETE FROM conversations WHERE id = ?", (row["id"],))
    return True


@app.get("/api/history")
async def customer_history(session_id: str):
    """پیام‌های گفتگوی جاری — تا با رفرش صفحه از دست نروند."""
    return {"messages": chat_service.conversation_messages(session_id, "public")}


@app.get("/api/conversations")
async def customer_conversations(client_id: str):
    """فهرست گفتگوهای قبلیِ همین مرورگر."""
    return {"conversations": chat_service.recent_conversations(client_id, "public")}


@app.delete("/api/conversations/{session_id}")
async def delete_customer_conversation(session_id: str, client_id: str):
    if not _delete_conversation(session_id, client_id, "public"):
        raise HTTPException(status_code=404, detail="گفتگو پیدا نشد.")
    return {"ok": True}


@app.post("/api/feedback")
async def feedback(payload: FeedbackIn):
    value = 1 if payload.value > 0 else -1
    db.execute("UPDATE messages SET feedback = ? WHERE id = ?", (value, payload.message_id))
    return {"ok": True}


@app.post("/api/ticket")
async def create_ticket(payload: TicketIn):
    conv = db.query_one(
        "SELECT id FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (payload.session_id,),
    )
    ticket_id = db.execute(
        "INSERT INTO tickets(conv_id, name, contact, subject, body) VALUES (?, ?, ?, ?, ?)",
        (
            conv["id"] if conv else None,
            payload.name.strip()[:80],
            payload.contact.strip()[:120],
            (payload.subject or "درخواست تماس با پشتیبانی").strip()[:200],
            payload.body.strip()[:4000],
        ),
    )
    return {"ok": True, "ticket_id": ticket_id}


# ==================================================================
# ورود
# ==================================================================
@app.post("/api/auth/login")
async def login(payload: LoginIn):
    token = security.login(payload.role, payload.password)
    return {"token": token, "role": payload.role}


@app.get("/api/auth/me")
async def me(role: str = Depends(security.require_staff)):
    return {"role": role}


# ==================================================================
# کنسول پشتیبان
# ==================================================================
@app.get("/api/agent/bootstrap")
async def agent_bootstrap(role: str = Depends(security.require_staff)):
    return {
        "brand": config.BRAND_NAME,
        "welcome": db.get_setting("welcome_agent", ""),
        "suggestions": _suggestions("agent_suggestions"),
        "model": settings.chat_model(),
        "stats": rag.stats(),
        "role": role,
    }


@app.post("/api/agent/chat")
async def agent_chat(payload: ChatIn, role: str = Depends(security.require_staff)):
    return StreamingResponse(
        chat_service.answer_stream(
            payload.message.strip(),
            session_id=payload.session_id,
            audience="internal",
            model=payload.model,
            client_id=payload.client_id,
            length=payload.length,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/agent/history")
async def agent_history(session_id: str, role: str = Depends(security.require_staff)):
    return {"messages": chat_service.conversation_messages(session_id, "internal")}


@app.get("/api/agent/conversations")
async def agent_conversations(client_id: str, role: str = Depends(security.require_staff)):
    return {"conversations": chat_service.recent_conversations(client_id, "internal")}


@app.delete("/api/agent/conversations/{session_id}")
async def delete_agent_conversation(
    session_id: str, client_id: str, role: str = Depends(security.require_staff)
):
    if not _delete_conversation(session_id, client_id, "internal"):
        raise HTTPException(status_code=404, detail="گفتگو پیدا نشد.")
    return {"ok": True}


@app.post("/api/agent/rewrite")
async def agent_rewrite(payload: RewriteIn, role: str = Depends(security.require_staff)):
    """پاسخ فنی را به متن قابل ارسال برای مشتری تبدیل می‌کند."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="متنی برای بازنویسی داده نشد.")
    try:
        result = await avalai.chat(
            [
                {"role": "system", "content": prompts.REWRITE_FOR_CUSTOMER},
                {"role": "user", "content": text},
            ],
            temperature=0.4,
        )
    except avalai.AvalAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"text": result}


@app.get("/api/agent/search")
async def agent_search(q: str, role: str = Depends(security.require_staff)):
    hits = await rag.search(q, audience="internal", top_k=10)
    return {
        "results": [
            {
                "title": h.title,
                "page": h.page,
                "score": round(h.score, 3),
                "text": h.text[:1200],
            }
            for h in hits
        ]
    }


@app.get("/api/agent/documents")
async def agent_documents(role: str = Depends(security.require_staff)):
    rows = db.query(
        "SELECT id, title, audience, pages, chunk_count, status FROM documents ORDER BY title"
    )
    return {"documents": [dict(r) for r in rows]}


# ==================================================================
# پنل مدیریت
# ==================================================================
def _safe_name(name: str) -> str:
    name = unicodedata.normalize("NFC", Path(name).name)
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]", "_", name).strip()
    return name[:150] or "file"


async def _index_in_background(doc_id: int) -> None:
    try:
        await rag.index_document(doc_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[index] سند {doc_id} ایندکس نشد: {exc}")


def _schedule_index(doc_id: int) -> None:
    db.execute(
        "UPDATE documents SET status = 'indexing', progress = 'در صف پردازش…' WHERE id = ?",
        (doc_id,),
    )
    asyncio.create_task(_index_in_background(doc_id))


def _doc_row(row) -> dict:
    data = dict(row)
    data["size_mb"] = round((data.get("size_bytes") or 0) / (1024 * 1024), 2)
    return data


@app.get("/api/admin/documents")
async def list_documents(role: str = Depends(security.require_admin)):
    rows = db.query("SELECT * FROM documents ORDER BY id DESC")
    return {"documents": [_doc_row(r) for r in rows]}


@app.post("/api/admin/documents")
async def upload_documents(
    files: list[UploadFile] = File(...),
    audience: str = Form("both"),
    category: str = Form(""),
    ai_repair: str = Form("true"),
    role: str = Depends(security.require_admin),
):
    if audience not in AUDIENCES:
        raise HTTPException(status_code=400, detail="مخاطب نامعتبر است.")

    results = []
    for upload in files:
        name = _safe_name(upload.filename or "file")
        ext = Path(name).suffix.lower()
        if ext not in ingest.SUPPORTED_EXTENSIONS:
            results.append({"file": name, "ok": False, "error": f"فرمت {ext} پشتیبانی نمی‌شود."})
            continue

        target = config.UPLOAD_DIR / name
        counter = 1
        while target.exists():
            target = config.UPLOAD_DIR / f"{Path(name).stem}-{counter}{ext}"
            counter += 1

        try:
            with open(target, "wb") as out:
                shutil.copyfileobj(upload.file, out, length=1 << 20)
        finally:
            await upload.close()

        size = target.stat().st_size
        if size > config.MAX_UPLOAD_MB * 1024 * 1024:
            target.unlink(missing_ok=True)
            results.append(
                {"file": name, "ok": False, "error": f"حجم فایل بیشتر از {config.MAX_UPLOAD_MB} مگابایت است."}
            )
            continue

        doc_id = db.execute(
            "INSERT INTO documents(title, filename, path, audience, category, size_bytes, ai_repair) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                Path(target.name).stem,
                target.name,
                str(target),
                audience,
                category.strip(),
                size,
                1 if str(ai_repair).lower() in {"1", "true", "on", "yes"} else 0,
            ),
        )
        _schedule_index(doc_id)
        results.append({"file": target.name, "ok": True, "doc_id": doc_id, "queued": True})

    return {"results": results, "stats": rag.stats()}


@app.post("/api/admin/documents/import-folder")
async def import_folder(role: str = Depends(security.require_admin)):
    """فایل‌های موجود در پوشه‌ی docs را وارد سیستم می‌کند."""
    added, skipped = [], []
    for path in sorted(config.DOCS_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in ingest.SUPPORTED_EXTENSIONS:
            continue
        exists = db.query_one("SELECT id FROM documents WHERE path = ?", (str(path),))
        if exists:
            skipped.append(path.name)
            continue
        doc_id = db.execute(
            "INSERT INTO documents(title, filename, path, audience, size_bytes) "
            "VALUES (?, ?, ?, 'both', ?)",
            (path.stem, path.name, str(path), path.stat().st_size),
        )
        _schedule_index(doc_id)
        added.append({"file": path.name, "doc_id": doc_id, "queued": True})
    return {"added": added, "skipped": skipped, "stats": rag.stats()}


@app.patch("/api/admin/documents/{doc_id}")
async def patch_document(
    doc_id: int, payload: DocPatchIn, role: str = Depends(security.require_admin)
):
    row = db.query_one("SELECT id FROM documents WHERE id = ?", (doc_id,))
    if not row:
        raise HTTPException(status_code=404, detail="سند پیدا نشد.")
    if payload.audience and payload.audience not in AUDIENCES:
        raise HTTPException(status_code=400, detail="مخاطب نامعتبر است.")

    updates, params = [], []
    for field_name, value in (
        ("title", payload.title),
        ("audience", payload.audience),
        ("category", payload.category),
    ):
        if value is not None:
            updates.append(f"{field_name} = ?")
            params.append(value.strip())
    if payload.ai_repair is not None:
        updates.append("ai_repair = ?")
        params.append(1 if payload.ai_repair else 0)
    if updates:
        params.append(doc_id)
        db.execute(
            f"UPDATE documents SET {', '.join(updates)}, updated_at = datetime('now') WHERE id = ?",
            params,
        )
        rag.invalidate_cache()
    return {"ok": True}


@app.post("/api/admin/documents/{doc_id}/reindex")
async def reindex_document(doc_id: int, role: str = Depends(security.require_admin)):
    if not db.query_one("SELECT id FROM documents WHERE id = ?", (doc_id,)):
        raise HTTPException(status_code=404, detail="سند پیدا نشد.")
    _schedule_index(doc_id)
    return {"ok": True, "queued": True}


@app.delete("/api/admin/documents/{doc_id}")
async def delete_document(doc_id: int, role: str = Depends(security.require_admin)):
    row = db.query_one("SELECT path FROM documents WHERE id = ?", (doc_id,))
    if not row:
        raise HTTPException(status_code=404, detail="سند پیدا نشد.")
    db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    path = Path(row["path"])
    if config.UPLOAD_DIR in path.parents:
        path.unlink(missing_ok=True)
    rag.invalidate_cache()
    return {"ok": True}


@app.get("/api/admin/stats")
async def admin_stats(role: str = Depends(security.require_admin)):
    counts = db.query_one(
        "SELECT "
        "(SELECT COUNT(*) FROM conversations WHERE audience='public') AS customer_chats, "
        "(SELECT COUNT(*) FROM conversations WHERE audience='internal') AS agent_chats, "
        "(SELECT COUNT(*) FROM messages WHERE role='user') AS questions, "
        "(SELECT COUNT(*) FROM messages WHERE role='assistant' AND grounded=0) AS unanswered, "
        "(SELECT COUNT(*) FROM messages WHERE feedback=1) AS likes, "
        "(SELECT COUNT(*) FROM messages WHERE feedback=-1) AS dislikes, "
        "(SELECT COUNT(*) FROM tickets WHERE status='open') AS open_tickets"
    )
    return {
        "index": rag.stats(),
        "usage": dict(counts),
        "model": settings.chat_model(),
        "embedding_model": settings.embedding_model(),
        "vision_model": settings.vision_model(),
        "vision_enabled": settings.vision_enabled(),
        "api_key_set": bool(settings.api_key()),
    }


@app.get("/api/admin/credit")
async def admin_credit(role: str = Depends(security.require_admin)):
    try:
        data = await avalai.credit()
    except avalai.AvalAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return data


@app.get("/api/admin/models")
async def admin_models(role: str = Depends(security.require_admin)):
    try:
        return {"models": await avalai.list_models()}
    except avalai.AvalAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/admin/conversations")
async def admin_conversations(
    audience: str = "public", limit: int = 50, role: str = Depends(security.require_admin)
):
    rows = db.query(
        "SELECT c.id, c.title, c.audience, c.created_at, "
        "(SELECT COUNT(*) FROM messages m WHERE m.conv_id = c.id) AS turns "
        "FROM conversations c WHERE c.audience = ? ORDER BY c.id DESC LIMIT ?",
        (audience, min(limit, 200)),
    )
    return {"conversations": [dict(r) for r in rows]}


@app.get("/api/admin/conversations/{conv_id}")
async def admin_conversation(conv_id: int, role: str = Depends(security.require_admin)):
    rows = db.query(
        "SELECT id, role, content, sources, grounded, feedback, latency_ms, created_at "
        "FROM messages WHERE conv_id = ? ORDER BY id",
        (conv_id,),
    )
    messages = []
    for r in rows:
        item = dict(r)
        try:
            item["sources"] = json.loads(item["sources"] or "[]")
        except json.JSONDecodeError:
            item["sources"] = []
        messages.append(item)
    return {"messages": messages}


@app.get("/api/admin/gaps")
async def admin_gaps(limit: int = 40, role: str = Depends(security.require_admin)):
    """سوالاتی که پاسخی در مستندات نداشتند — ورودی خوبی برای تکمیل راهنماها."""
    rows = db.query(
        "SELECT m2.content AS question, m1.created_at, c.audience "
        "FROM messages m1 "
        "JOIN messages m2 ON m2.id = ("
        "  SELECT MAX(id) FROM messages WHERE conv_id = m1.conv_id AND role='user' AND id < m1.id"
        ") "
        "JOIN conversations c ON c.id = m1.conv_id "
        "WHERE m1.role='assistant' AND (m1.grounded = 0 OR m1.feedback = -1) "
        "ORDER BY m1.id DESC LIMIT ?",
        (min(limit, 200),),
    )
    return {"gaps": [dict(r) for r in rows]}


@app.get("/api/admin/tickets")
async def admin_tickets(role: str = Depends(security.require_admin)):
    rows = db.query("SELECT * FROM tickets ORDER BY id DESC LIMIT 100")
    return {"tickets": [dict(r) for r in rows]}


@app.patch("/api/admin/tickets/{ticket_id}")
async def close_ticket(ticket_id: int, role: str = Depends(security.require_admin)):
    db.execute("UPDATE tickets SET status = 'done' WHERE id = ?", (ticket_id,))
    return {"ok": True}


@app.get("/api/admin/ai-settings")
async def get_ai_settings(role: str = Depends(security.require_admin)):
    return settings.public_view()


@app.put("/api/admin/ai-settings")
async def put_ai_settings(payload: AISettingsIn, role: str = Depends(security.require_admin)):
    values: dict[str, str] = {}
    for field_name in ("chat_model", "fast_model", "vision_model", "embedding_model"):
        value = getattr(payload, field_name)
        if value is not None:
            values[field_name] = value
    if payload.vision_enabled is not None:
        values["vision_enabled"] = "true" if payload.vision_enabled else "false"
    # کلید خالی یعنی «دست نزن»؛ برای پاک کردن باید صریحاً "-" فرستاده شود
    if payload.avalai_api_key is not None:
        key = payload.avalai_api_key.strip()
        if key == "-":
            values["avalai_api_key"] = ""
        elif key and not key.startswith("•"):
            values["avalai_api_key"] = key

    settings.save(values)
    rag.invalidate_cache()
    return settings.public_view()


@app.post("/api/admin/ai-test")
async def test_ai_settings(role: str = Depends(security.require_admin)):
    """همان تست‌های scripts/check_avalai.py، از داخل پنل."""
    return {"checks": await diagnostics.run_checks()}


@app.get("/api/admin/settings")
async def get_settings(role: str = Depends(security.require_admin)):
    rows = db.query("SELECT key, value FROM settings")
    return {"settings": {r["key"]: r["value"] for r in rows}}


@app.put("/api/admin/settings")
async def put_settings(payload: SettingsIn, role: str = Depends(security.require_admin)):
    for key, value in payload.values.items():
        db.set_setting(key, value)
    return {"ok": True}


# ==================================================================
# سلامت سرویس و رابط کاربری
# ==================================================================
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": settings.chat_model(),
        "api_key_set": bool(settings.api_key()),
        "index": rag.stats(),
    }


if config.WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=config.WEB_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def page_customer():
        return FileResponse(config.WEB_DIR / "index.html")

    @app.get("/agent", include_in_schema=False)
    async def page_agent():
        return FileResponse(config.WEB_DIR / "agent.html")

    @app.get("/admin", include_in_schema=False)
    async def page_admin():
        return FileResponse(config.WEB_DIR / "admin.html")
