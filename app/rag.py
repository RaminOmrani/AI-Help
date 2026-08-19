"""موتور جستجوی مستندات: ایندکس‌گذاری + بازیابی ترکیبی (معنایی + لغوی)."""

from __future__ import annotations

import asyncio
import math
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import avalai, config, db
from .ingest import chunk_pages, checksum, extract_pages
from .repair import repair_pages
from .textutils import normalize, snippet, tokens

_index_lock = threading.Lock()
_cache: dict[str, object] = {"version": None, "rows": None, "matrix": None, "df": None}


# ------------------------------------------------------------------
# ایندکس‌گذاری
# ------------------------------------------------------------------
def _set_status(doc_id: int, status: str, **fields) -> None:
    sets = ["status = ?", "updated_at = datetime('now')"]
    params: list[object] = [status]
    for key, value in fields.items():
        sets.append(f"{key} = ?")
        params.append(value)
    params.append(doc_id)
    db.execute(f"UPDATE documents SET {', '.join(sets)} WHERE id = ?", params)


def _progress(doc_id: int, text: str) -> None:
    db.execute("UPDATE documents SET progress = ? WHERE id = ?", (text, doc_id))


async def index_document(doc_id: int) -> dict:
    """متن سند را استخراج، بازسازی، تکه‌بندی و بردارگذاری می‌کند."""
    row = db.query_one("SELECT * FROM documents WHERE id = ?", (doc_id,))
    if not row:
        raise ValueError("سند پیدا نشد.")

    path = Path(row["path"])
    if not path.exists():
        _set_status(doc_id, "error", error="فایل روی دیسک پیدا نشد.")
        raise FileNotFoundError(path)

    _set_status(doc_id, "indexing", error="", progress="در حال خواندن فایل…")
    try:
        pages = await asyncio.to_thread(extract_pages, path)
    except Exception as exc:  # noqa: BLE001
        _set_status(doc_id, "error", error=f"خطا در خواندن فایل: {exc}", progress="")
        raise

    repaired = 0
    needs_ai_repair = path.suffix.lower() == ".pdf"  # فقط PDF متن شکسته می‌دهد
    if row["ai_repair"] and needs_ai_repair and config.AVALAI_API_KEY:
        _progress(doc_id, f"بازسازی متن با هوش مصنوعی (۰ از {len(pages)})…")

        def on_progress(done: int, total: int) -> None:
            _progress(doc_id, f"بازسازی متن با هوش مصنوعی ({done} از {total})…")

        try:
            pages, repaired = await repair_pages(pages, on_progress=on_progress)
        except Exception as exc:  # noqa: BLE001
            print(f"[rag] بازسازی متن ناموفق بود: {exc}")

    _progress(doc_id, "تکه‌بندی متن…")
    try:
        chunks = await asyncio.to_thread(chunk_pages, pages)
    except Exception as exc:  # noqa: BLE001
        _set_status(doc_id, "error", error=f"خطا در پردازش متن: {exc}", progress="")
        raise

    if not chunks:
        _set_status(
            doc_id,
            "error",
            error="هیچ متنی از فایل استخراج نشد. اگر PDF اسکن‌شده است، نسخه‌ی متنی یا OCR‌شده را بارگذاری کنید.",
            pages=len(pages),
            chunk_count=0,
            progress="",
        )
        return {"chunks": 0, "pages": len(pages), "embedded": False}

    db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    db.executemany(
        "INSERT INTO chunks(doc_id, page, ord, text, norm) VALUES (?, ?, ?, ?, ?)",
        [(doc_id, c.page, c.ord, c.text, normalize(c.text)) for c in chunks],
    )

    _progress(doc_id, f"ساخت بردارهای جستجو ({len(chunks)} تکه)…")
    embedded = await _embed_document(doc_id)
    _set_status(
        doc_id,
        "ready",
        pages=len(pages),
        chunk_count=len(chunks),
        repaired=repaired,
        progress="",
        embedded=1 if embedded else 0,
        checksum=await asyncio.to_thread(checksum, path),
        error="" if embedded else "بردارسازی انجام نشد؛ فعلاً جستجوی کلیدواژه‌ای فعال است.",
    )
    invalidate_cache()
    return {"chunks": len(chunks), "pages": len(pages), "embedded": embedded, "repaired": repaired}


async def _embed_document(doc_id: int) -> bool:
    rows = db.query("SELECT id, text FROM chunks WHERE doc_id = ? ORDER BY id", (doc_id,))
    if not rows:
        return False
    if not config.AVALAI_API_KEY:
        return False

    batch = config.EMBED_BATCH
    try:
        for start in range(0, len(rows), batch):
            slice_ = rows[start : start + batch]
            vectors = await avalai.embed([r["text"][:6000] for r in slice_])
            if len(vectors) != len(slice_):
                return False
            db.executemany(
                "UPDATE chunks SET embedding = ? WHERE id = ?",
                [
                    (np.asarray(vec, dtype=np.float32).tobytes(), row["id"])
                    for row, vec in zip(slice_, vectors)
                ],
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[rag] بردارسازی ناموفق بود: {exc}")
        return False
    return True


def invalidate_cache() -> None:
    with _index_lock:
        _cache.update({"version": None, "rows": None, "matrix": None, "df": None})


# ------------------------------------------------------------------
# بارگذاری ایندکس در حافظه
# ------------------------------------------------------------------
def _fingerprint() -> str:
    row = db.query_one(
        "SELECT COUNT(*) AS c, COALESCE(MAX(id), 0) AS m FROM chunks"
    )
    docs = db.query_one(
        "SELECT COUNT(*) AS c, COALESCE(MAX(updated_at), '') AS u FROM documents"
    )
    return f"{row['c']}-{row['m']}-{docs['c']}-{docs['u']}"


def _load() -> tuple[list[dict], np.ndarray | None, Counter]:
    fingerprint = _fingerprint()
    with _index_lock:
        if _cache["version"] == fingerprint:
            return _cache["rows"], _cache["matrix"], _cache["df"]  # type: ignore[return-value]

    raw = db.query(
        """
        SELECT c.id, c.doc_id, c.page, c.text, c.norm, c.embedding,
               d.title, d.filename, d.audience, d.category
        FROM chunks c JOIN documents d ON d.id = c.doc_id
        WHERE d.status = 'ready'
        ORDER BY c.id
        """
    )

    rows: list[dict] = []
    vectors: list[np.ndarray] = []
    df: Counter = Counter()
    dim = None

    for r in raw:
        toks = r["norm"].split()
        rows.append(
            {
                "id": r["id"],
                "doc_id": r["doc_id"],
                "page": r["page"],
                "text": r["text"],
                "title": r["title"],
                "filename": r["filename"],
                "audience": r["audience"],
                "category": r["category"],
                "tokens": Counter(toks),
                "length": max(len(toks), 1),
            }
        )
        df.update(set(toks))
        if r["embedding"]:
            vec = np.frombuffer(r["embedding"], dtype=np.float32)
            dim = dim or vec.size
            vectors.append(vec if vec.size == dim else np.zeros(dim, dtype=np.float32))
        else:
            vectors.append(None)  # type: ignore[arg-type]

    matrix = None
    if dim:
        matrix = np.zeros((len(rows), dim), dtype=np.float32)
        for i, vec in enumerate(vectors):
            if vec is not None and vec.size == dim:
                matrix[i] = vec
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms

    with _index_lock:
        _cache.update({"version": fingerprint, "rows": rows, "matrix": matrix, "df": df})
    return rows, matrix, df


# ------------------------------------------------------------------
# جستجو
# ------------------------------------------------------------------
@dataclass
class Hit:
    chunk_id: int
    doc_id: int
    title: str
    filename: str
    page: int
    text: str
    score: float
    lexical: float = 0.0
    semantic: float = 0.0
    tags: list[str] = field(default_factory=list)

    def as_source(self) -> dict:
        return {
            "id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.title,
            "page": self.page,
            "score": round(self.score, 4),
            "snippet": snippet(self.text, 260),
        }


def _lexical_scores(query: str, rows: list[dict], df: Counter) -> np.ndarray:
    scores = np.zeros(len(rows), dtype=np.float32)
    q_tokens = tokens(query)
    if not q_tokens:
        return scores

    total = max(len(rows), 1)
    avg_len = sum(r["length"] for r in rows) / total if rows else 1.0
    k1, b = 1.4, 0.72

    for i, row in enumerate(rows):
        score = 0.0
        for token in q_tokens:
            freq = row["tokens"].get(token, 0)
            if not freq:
                # تطبیق جزئی برای واژه‌های ترکیبی فارسی
                partial = sum(
                    count for term, count in row["tokens"].items()
                    if len(token) > 3 and token in term
                )
                if not partial:
                    continue
                freq = min(partial, 2) * 0.4
            idf = math.log(1 + (total - df.get(token, 0) + 0.5) / (df.get(token, 0) + 0.5))
            denom = freq + k1 * (1 - b + b * row["length"] / max(avg_len, 1.0))
            score += idf * (freq * (k1 + 1)) / max(denom, 1e-6)
        scores[i] = score
    return scores


async def search(
    query: str,
    *,
    audience: str = "internal",
    top_k: int | None = None,
) -> list[Hit]:
    """بازیابی ترکیبی: امتیاز معنایی + امتیاز کلیدواژه‌ای."""
    rows, matrix, df = _load()
    if not rows:
        return []

    top_k = top_k or config.TOP_K
    allowed = {"both", audience}
    mask = np.array([r["audience"] in allowed for r in rows], dtype=bool)
    if not mask.any():
        return []

    lexical = _lexical_scores(query, rows, df)
    semantic = np.zeros(len(rows), dtype=np.float32)

    if matrix is not None and config.AVALAI_API_KEY:
        try:
            vectors = await avalai.embed([query])
            if vectors:
                q = np.asarray(vectors[0], dtype=np.float32)
                if q.size == matrix.shape[1]:
                    q = q / (np.linalg.norm(q) or 1.0)
                    semantic = matrix @ q
        except Exception as exc:  # noqa: BLE001
            print(f"[rag] جستجوی معنایی در دسترس نیست: {exc}")

    lex_norm = lexical / (lexical.max() or 1.0)
    sem_norm = np.clip(semantic, 0, None)
    sem_norm = sem_norm / (sem_norm.max() or 1.0)

    weight = 0.6 if semantic.any() else 0.0
    combined = weight * sem_norm + (1 - weight) * lex_norm
    combined = np.where(mask, combined, -1.0)

    order = np.argsort(-combined)[: top_k * 2]
    hits: list[Hit] = []
    seen_pages: set[tuple[int, int]] = set()

    for idx in order:
        if combined[idx] <= 0.02:
            continue
        row = rows[idx]
        key = (row["doc_id"], row["page"])
        if key in seen_pages and len(hits) >= top_k // 2:
            continue
        seen_pages.add(key)
        hits.append(
            Hit(
                chunk_id=row["id"],
                doc_id=row["doc_id"],
                title=row["title"],
                filename=row["filename"],
                page=row["page"],
                text=row["text"],
                score=float(combined[idx]),
                lexical=float(lex_norm[idx]),
                semantic=float(sem_norm[idx]),
            )
        )
        if len(hits) >= top_k:
            break
    return hits


def build_context(hits: list[Hit], *, max_chars: int = 14000) -> str:
    parts: list[str] = []
    used = 0
    for i, hit in enumerate(hits, start=1):
        block = (
            f"[منبع {i}] فایل: «{hit.title}» — صفحه {hit.page}\n"
            f"{hit.text.strip()}\n"
        )
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n---\n".join(parts)


def stats() -> dict:
    docs = db.query_one(
        "SELECT COUNT(*) AS total, "
        "SUM(status = 'ready') AS ready, "
        "SUM(status = 'error') AS failed, "
        "COALESCE(SUM(pages), 0) AS pages FROM documents"
    )
    chunks = db.query_one(
        "SELECT COUNT(*) AS total, SUM(embedding IS NOT NULL) AS embedded FROM chunks"
    )
    return {
        "documents": docs["total"] or 0,
        "ready": docs["ready"] or 0,
        "failed": docs["failed"] or 0,
        "pages": docs["pages"] or 0,
        "chunks": chunks["total"] or 0,
        "embedded_chunks": chunks["embedded"] or 0,
    }
