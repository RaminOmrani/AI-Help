"""تست سلامت خط لوله، بدون نیاز به کلید یا اینترنت.

سرویس AvalAI با یک نسخه‌ی ساختگی جایگزین می‌شود تا بشود بدون هزینه بررسی کرد که
ایندکس‌گذاری، تفکیک دسترسی مشتری/پشتیبان، استریم پاسخ و ذخیره‌ی گفتگو درست کار می‌کنند.

    python scripts/selftest.py
"""

import asyncio
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WORK = Path(tempfile.mkdtemp(prefix="support-ai-selftest-"))
os.environ['DB_PATH'] = str(WORK / 'test.db')
os.environ['DATA_DIR'] = str(WORK)
os.environ['DOCS_DIR'] = str(WORK / 'docs')
os.environ['AVALAI_API_KEY'] = 'aa-fake-key-for-testing'

from app import avalai, config, db, rag, chat_service, repair, vision  # noqa: E402

calls = {"chat": 0, "embed": 0, "stream": 0, "vision": 0, "image_bytes": []}


def fake_vector(text, dim=64):
    """بردار قطعی بر پایه‌ی کلمات — تا شباهت معنایی قابل تست باشد."""
    vec = [0.0] * dim
    for word in text.split():
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    return vec


async def fake_embed(texts, model=None):
    calls["embed"] += 1
    return [fake_vector(t) for t in texts]


async def fake_chat(messages, model=None, temperature=0.0, max_tokens=None):
    calls["chat"] += 1
    user = messages[-1]["content"]
    # درخواست بینایی: محتوا لیستی شامل تصویر است
    if isinstance(user, list):
        image = next((c for c in user if c.get("type") == "image_url"), None)
        assert image, "تصویری به مدل بینایی نرسید"
        url = image["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,"), "قالب تصویر درست نیست"
        raw = base64.b64decode(url.split(",", 1)[1])
        assert raw[:3] == b"\xff\xd8\xff", "تصویر JPEG معتبر نیست"
        calls["vision"] += 1
        calls["image_bytes"].append(len(raw))
        return "متن تمیزشده‌ی صفحه.\n\nتصویر: پنجره‌ی Welcome نصب SQL Server — دکمه‌ی Next را بزنید."
    if messages[0]["content"].startswith("تو یک ابزار بازسازی"):
        return user.replace("سواالت", "سوالات").replace("کاال", "کالا")
    return "پاسخ ساختگی"


async def fake_stream(messages, model=None, temperature=0.0, max_tokens=None):
    calls["stream"] += 1
    context = messages[-1]["content"]
    assert "### مستندات" in context, "بلوک مستندات به مدل نرسید"
    for piece in ["۱. ", "منوی فروش ", "را باز کنید.\n", "۲. دکمه‌ی جدید را بزنید."]:
        yield piece


avalai.embed = fake_embed
avalai.chat = fake_chat
avalai.chat_stream = fake_stream
repair.avalai.chat = fake_chat
vision.avalai.chat = fake_chat
rag.avalai.embed = fake_embed
chat_service.avalai.chat_stream = fake_stream


async def main():
    db.init_db()
    ok = True

    # ---- سند داخلی (SQL) و سند عمومی ----
    internal = str(WORK / 'internal.txt')
    public = str(WORK / 'public.txt')
    open(internal, 'w', encoding='utf-8').write(
        "رمز عبور را فراموش کردم؟\nدستور زیر را در Database اجرا کنید: delete from log1 where kcod=1\n"
        "این روش فقط برای کارشناسان است.\n" * 3
    )
    open(public, 'w', encoding='utf-8').write(
        "چگونه فاکتور برگشت از فروش ثبت کنم؟\nمنوی فروش را باز کنید و گزینه‌ی برگشت از فروش را بزنید.\n"
        "سپس کالا را انتخاب و ذخیره کنید.\n" * 3
    )

    doc_internal = db.execute(
        "INSERT INTO documents(title, filename, path, audience, size_bytes) VALUES (?,?,?,?,?)",
        ("راهنمای داخلی", "internal.txt", internal, "internal", os.path.getsize(internal)))
    doc_public = db.execute(
        "INSERT INTO documents(title, filename, path, audience, size_bytes) VALUES (?,?,?,?,?)",
        ("راهنمای مشتری", "public.txt", public, "public", os.path.getsize(public)))

    r1 = await rag.index_document(doc_internal)
    r2 = await rag.index_document(doc_public)
    print("ایندکس:", r1, r2)
    assert r1["embedded"] and r2["embedded"], "بردارسازی انجام نشد"

    embedded = db.query_one("SELECT COUNT(*) c FROM chunks WHERE embedding IS NOT NULL")["c"]
    print(f"✅ {embedded} تکه بردارگذاری شد ({calls['embed']} فراخوانی embed)")

    # ---- تفکیک دسترسی ----
    public_hits = await rag.search("رمز عبور فراموش کردم", audience="public")
    internal_hits = await rag.search("رمز عبور فراموش کردم", audience="internal")
    leaked = [h for h in public_hits if h.doc_id == doc_internal]
    if leaked:
        print("❌ نشت اطلاعات داخلی به مشتری!"); ok = False
    else:
        print(f"✅ تفکیک دسترسی درست است (مشتری {len(public_hits)} منبع، پشتیبان {len(internal_hits)} منبع)")
    assert any(h.doc_id == doc_internal for h in internal_hits), "پشتیبان سند داخلی را ندید"

    # ---- استریم پاسخ ----
    events = []
    async for raw in chat_service.answer_stream(
        "چطور فاکتور برگشت از فروش ثبت کنم؟", session_id="s1", audience="public"
    ):
        events.append(json.loads(raw[5:].strip()))
    kinds = [e["type"] for e in events]
    print("رویدادها:", kinds)
    assert kinds[0] == "sources" and kinds[-1] == "done", "ترتیب رویدادها درست نیست"
    answer = "".join(e["text"] for e in events if e["type"] == "delta")
    assert answer, "متن پاسخ خالی است"
    print(f"✅ استریم کار می‌کند → {answer[:45]}…")

    # ---- ذخیره در دیتابیس ----
    msgs = db.query("SELECT role, content, sources, grounded FROM messages ORDER BY id")
    assert len(msgs) == 2 and msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant"
    assert json.loads(msgs[1]["sources"]), "منابع ذخیره نشد"
    print(f"✅ گفتگو در دیتابیس ذخیره شد ({len(msgs)} پیام، منابع ثبت شد)")

    # ---- حافظه‌ی گفتگو ----
    async for _ in chat_service.answer_stream("و بعدش؟", session_id="s1", audience="public"):
        pass
    total = db.query_one("SELECT COUNT(*) c FROM messages")["c"]
    assert total == 4, f"انتظار ۴ پیام، دریافت {total}"
    convs = db.query_one("SELECT COUNT(*) c FROM conversations")["c"]
    assert convs == 1, "برای یک نشست بیش از یک گفتگو ساخته شد"
    print("✅ حافظه‌ی گفتگو روی یک نشست حفظ شد")

    # ---- بازسازی متن ----
    broken = "چجور ی کاالها ی داخل سرور رو ببر می داخل س ی ستم نت ی کال صندوق سواالت " * 4
    fixed, count = await repair.repair_pages([broken])
    assert count == 1 and "سوالات" in fixed[0], "بازسازی متن شکسته کار نکرد"
    clean = "منوی فروش را باز کنید و گزینه‌ی برگشت از فروش را بزنید. کالا را ذخیره کنید. " * 6
    _, skipped = await repair.repair_pages([clean])
    assert skipped == 0, "متن سالم بی‌دلیل به مدل فرستاده شد"
    print("✅ بازسازی متن فقط روی صفحه‌های شکسته اجرا می‌شود")

    # ---- خواندن تصویری صفحه‌های PDF ----
    guide = next(
        (p for p in Path("docs").glob("*.pdf") if vision.pages_with_images(p)), None
    ) if Path("docs").exists() else None

    if guide:
        vision.config.VISION_MAX_PAGES = 2  # برای سرعت تست
        doc_pdf = db.execute(
            "INSERT INTO documents(title, filename, path, audience, size_bytes) VALUES (?,?,?,?,?)",
            (guide.stem, guide.name, str(guide), "internal", guide.stat().st_size))
        before = calls["vision"]
        info = await rag.index_document(doc_pdf)
        assert info["vision_pages"] == 2, f"انتظار ۲ صفحه‌ی تصویری، دریافت {info['vision_pages']}"
        assert calls["vision"] - before == 2, "مدل بینایی فراخوانی نشد"
        avg_kb = sum(calls["image_bytes"]) // len(calls["image_bytes"]) // 1024
        found = db.query_one("SELECT page FROM chunks WHERE text LIKE '%Welcome%' LIMIT 1")
        assert found, "متنِ آمده از تصویر وارد ایندکس نشد"
        print(f"✅ اسکرین‌شات‌ها خوانده و ایندکس شدند "
              f"({info['vision_pages']} صفحه، میانگین {avg_kb} کیلوبایت، صفحه‌ی {found['page']})")
    else:
        print("• تست بینایی رد شد (فایل PDF عکس‌داری در پوشه‌ی docs نبود)")

    # ---- حذف سند ----
    db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_public,))
    db.execute("DELETE FROM documents WHERE id = ?", (doc_public,))
    rag.invalidate_cache()
    remaining = await rag.search("فاکتور برگشت از فروش", audience="public")
    assert not [h for h in remaining if h.doc_id == doc_public], "تکه‌های سند حذف‌شده باقی ماند"
    print("✅ حذف سند، تکه‌هایش را هم پاک می‌کند")

    print("\n" + ("همه‌ی تست‌ها موفق ✅" if ok else "برخی تست‌ها ناموفق ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    raise SystemExit(code)
