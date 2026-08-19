#!/usr/bin/env python3
"""مقایسه‌ی مدل‌های زبانی روی مستندات واقعی خودتان.

به‌جای حدس زدن اینکه «کدام مدل بهتر است»، این اسکریپت چند سوال واقعی را از
مسیر کاملِ RAG عبور می‌دهد، پاسخ هر مدل را کنار هم می‌گذارد و **هزینه‌ی
واقعی تومانی** هر مدل را از تفاضل اعتبار حساب AvalAI حساب می‌کند.

    # مقایسه‌ی چند مدل با سوال‌های پیش‌فرض
    python scripts/compare_models.py gemini-3.7-flash gemini-3.5-flash

    # با سوال‌های خودتان
    python scripts/compare_models.py --ask "چطور بکاپ بگیرم؟" --ask "خطای اتصال به SQL" مدل۱ مدل۲

    # برای دستیار پشتیبان به‌جای مشتری
    python scripts/compare_models.py --audience internal gemini-3.7-flash

خروجی علاوه بر ترمینال، در قالب یک صفحه‌ی HTML هم ذخیره می‌شود تا بتوانید
پاسخ‌ها را با آرامش کنار هم بخوانید.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import avalai, config, db, prompts, rag, settings  # noqa: E402

DEFAULT_QUESTIONS_PUBLIC = [
    "چطور از اطلاعاتم پشتیبان (بکاپ) بگیرم؟",
    "رمز ورود برنامه را فراموش کرده‌ام، چه کار کنم؟",
    "چطور فاکتور برگشت از فروش ثبت کنم؟",
]
DEFAULT_QUESTIONS_INTERNAL = [
    "خطای اتصال به SQL Server چه دلایلی دارد و چطور رفعش کنم؟",
    "مراحل نصب کالر آی‌دی را بگو",
    "چطور یک جدول را از یک دیتابیس به دیتابیس دیگر منتقل کنم؟",
]


async def _credit_irt() -> float | None:
    """مانده‌ی اعتبار تومانی — برای اندازه‌گیری هزینه‌ی واقعی."""
    try:
        data = await avalai.credit()
        return float(data.get("remaining_irt") or 0)
    except Exception:  # noqa: BLE001
        return None


async def ask_one(question: str, model: str, audience: str) -> dict:
    """یک سوال را از کل مسیر RAG عبور می‌دهد و پاسخ مدل را برمی‌گرداند."""
    hits = await rag.search(question, audience=audience)
    context = rag.build_context(hits)
    system = prompts.customer_system() if audience == "public" else prompts.agent_system()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompts.user_turn(question, context, audience=audience)},
    ]

    started = time.time()
    meta: dict = {}
    try:
        answer = await avalai.chat(
            messages,
            model=model,
            temperature=0.2 if audience == "internal" else 0.35,
            max_tokens=config.ANSWER_MAX_TOKENS,
            meta=meta,
        )
        error = ""
        if meta.get("finish_reason") == "length":
            error = "⚠️ پاسخ به سقف طول رسید و ناقص است."
    except Exception as exc:  # noqa: BLE001
        answer, error = "", str(exc)

    return {
        "question": question,
        "answer": answer,
        "error": error,
        "seconds": round(time.time() - started, 1),
        "sources": [f"{h.title} — ص{h.page}" for h in hits[:3]],
        "chars": len(answer),
    }


async def run_model(model: str, questions: list[str], audience: str) -> dict:
    print(f"\n{'═' * 62}\n  مدل: {model}\n{'═' * 62}")
    before = await _credit_irt()
    results = []

    for question in questions:
        result = await ask_one(question, model, audience)
        results.append(result)
        if result["error"]:
            print(f"  ❌ {question}\n     {result['error'][:150]}")
        else:
            preview = result["answer"].replace("\n", " ")[:110]
            print(f"  ✅ [{result['seconds']}s] {question}\n     {preview}…")

    after = await _credit_irt()
    cost = round(before - after) if (before is not None and after is not None) else None
    ok = [r for r in results if r["answer"]]

    if cost is not None:
        per = round(cost / len(questions)) if questions else 0
        print(f"\n  💰 هزینه: {cost:,} تومان برای {len(questions)} سوال (میانگین {per:,} تومان)")
    if ok:
        avg_time = round(sum(r["seconds"] for r in ok) / len(ok), 1)
        avg_len = round(sum(r["chars"] for r in ok) / len(ok))
        print(f"  ⏱  میانگین زمان: {avg_time} ثانیه   |   میانگین طول پاسخ: {avg_len} نویسه")

    return {
        "model": model,
        "results": results,
        "cost_irt": cost,
        "failed": len(results) - len(ok),
    }


def write_report(runs: list[dict], questions: list[str], path: Path) -> None:
    esc = html.escape
    rows = []
    for i, question in enumerate(questions):
        cells = []
        for run in runs:
            r = run["results"][i]
            body = (
                (f'<p class="err">{esc(r["error"][:300])}</p>' if r["error"] else "")
                + (f'<pre>{esc(r["answer"])}</pre>'
                   f'<div class="meta">{r["seconds"]} ثانیه · {r["chars"]} نویسه</div>'
                   if r["answer"] else "")
            )
            cells.append(f"<td>{body}</td>")
        rows.append(
            f'<tr><th class="q">{esc(question)}<div class="meta">منابع: '
            f'{esc("، ".join(runs[0]["results"][i]["sources"]) or "—")}</div></th>'
            + "".join(cells)
            + "</tr>"
        )

    headers = "".join(
        f'<th>{esc(r["model"])}<div class="meta">'
        + (f'{r["cost_irt"]:,} تومان' if r["cost_irt"] is not None else "هزینه نامشخص")
        + (f' · {r["failed"]} خطا' if r["failed"] else "")
        + "</div></th>"
        for r in runs
    )

    path.write_text(
        f"""<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<title>مقایسه‌ی مدل‌ها</title><style>
body{{font-family:Vazirmatn,Tahoma,sans-serif;background:#faf7f2;color:#2a2521;padding:26px;line-height:1.9}}
h1{{font-size:20px}} table{{border-collapse:collapse;width:100%;background:#fff;border-radius:14px;overflow:hidden}}
th,td{{border:1px solid #e8e0d5;padding:13px;text-align:right;vertical-align:top;font-size:13.5px}}
thead th{{background:#0f7d76;color:#fff}} th.q{{background:#f2ede5;width:210px}}
pre{{white-space:pre-wrap;font-family:inherit;margin:0}} .meta{{font-size:11px;opacity:.65;margin-top:6px;font-weight:400}}
.err{{color:#c2410c;margin:0}}</style></head><body>
<h1>مقایسه‌ی مدل‌ها روی مستندات شما</h1>
<table><thead><tr><th class="q">سوال</th>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table>
</body></html>""",
        encoding="utf-8",
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description="مقایسه‌ی مدل‌ها روی مستندات واقعی")
    parser.add_argument("models", nargs="*", help="نام مدل‌ها (پیش‌فرض: مدل تنظیم‌شده در .env)")
    parser.add_argument("--ask", action="append", default=[], help="سوال دلخواه (قابل تکرار)")
    parser.add_argument(
        "--audience", choices=["public", "internal"], default="public",
        help="public = دستیار مشتری، internal = دستیار پشتیبان",
    )
    parser.add_argument("--out", default="model-comparison.html", help="مسیر گزارش HTML")
    args = parser.parse_args()

    db.init_db()
    if not settings.api_key():
        print("❌ کلید AvalAI ثبت نشده است — در پنل مدیریت یا فایل .env واردش کنید.")
        return 1

    if rag.stats()["ready"] == 0:
        print("❌ هنوز سندی ایندکس نشده. اول از پنل مدیریت فایل‌ها را بارگذاری کنید.")
        return 1

    models = args.models or [settings.chat_model()]
    questions = args.ask or (
        DEFAULT_QUESTIONS_PUBLIC if args.audience == "public" else DEFAULT_QUESTIONS_INTERNAL
    )

    print(f"\n{len(questions)} سوال × {len(models)} مدل — مخاطب: "
          f"{'مشتری' if args.audience == 'public' else 'پشتیبان'}")

    runs = [await run_model(m, questions, args.audience) for m in models]

    print(f"\n{'═' * 62}\n  جمع‌بندی\n{'═' * 62}")
    for run in sorted(runs, key=lambda r: (r["failed"], r["cost_irt"] or 0)):
        cost = f"{run['cost_irt']:,} تومان" if run["cost_irt"] is not None else "—"
        status = f"{run['failed']} خطا" if run["failed"] else "بدون خطا"
        print(f"  {run['model']:<32} {cost:>18}   {status}")

    out = Path(args.out)
    write_report(runs, questions, out)
    print(f"\n📄 گزارش کامل: {out.resolve()}")
    print("   کیفیت پاسخ را خودتان قضاوت کنید — عدد نمی‌تواند جای خواندن را بگیرد.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
