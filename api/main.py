"""Orchestration DB — REST API

Run locally:
    pip install -r requirements.txt
    uvicorn api.main:app --reload      # http://127.0.0.1:8000
    # Interactive docs: http://127.0.0.1:8000/docs

Authentication:
    Set API_KEY env var. Every request must include:
        X-API-Key: <your-key>
    Unset API_KEY (e.g. local dev) → auth disabled.

For a full SQL query UI (ad-hoc queries, table browsing):
    datasette orchestration.db        # http://127.0.0.1:8001
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from instrdb.db import DB_PATH, get_connection

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_API_KEY = os.environ.get("API_KEY")  # None → auth disabled (local dev)
_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_key(key: Optional[str] = Security(_key_header)):
    if _API_KEY and key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

app = FastAPI(
    title="Orchestration DB",
    description="Queryable database of orchestral instrumentation for the classical repertoire.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Unauthenticated — used by Railway's healthcheck
@app.get("/health", include_in_schema=False)
@app.get("/-/health", include_in_schema=False)
def health():
    return {"status": "ok"}

# All data routes go on this router — auth is enforced here
from fastapi import APIRouter
router = APIRouter(dependencies=[Depends(_require_key)])


def _db() -> sqlite3.Connection:
    if not Path(DB_PATH).exists():
        raise HTTPException(
            status_code=503,
            detail="Database not initialised. Run: python -m instrdb.migrate",
        )
    return get_connection()


# ---------------------------------------------------------------------------
# /composers
# ---------------------------------------------------------------------------

@router.get("/composers", summary="List all composers with work counts")
def list_composers():
    conn = _db()
    rows = conn.execute("""
        SELECT c.name, c.slug, COUNT(w.id) AS work_count
        FROM composers c
        JOIN works w ON w.composer_id = c.id
        GROUP BY c.id
        ORDER BY c.name
    """).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# /instruments
# ---------------------------------------------------------------------------

@router.get("/instruments", summary="List all instruments with how many works require them")
def list_instruments():
    conn = _db()
    rows = conn.execute("""
        SELECT instrument, family,
               COUNT(DISTINCT work_id) AS work_count
        FROM work_instruments
        WHERE is_doubling = 0
        GROUP BY instrument
        ORDER BY work_count DESC, instrument
    """).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# /works
# ---------------------------------------------------------------------------

@router.get("/works", summary="Search and filter works")
def list_works(
    composer: Optional[str] = Query(None, description="Exact composer name, e.g. 'Brahms, Johannes'"),
    instrument: Optional[str] = Query(None, description="Instrument key, e.g. 'horn', 'contrabassoon'"),
    instrument_count: Optional[int] = Query(None, description="Exact player count for the instrument filter"),
    year_from: Optional[int] = Query(None, description="Earliest composition year"),
    year_to: Optional[int] = Query(None, description="Latest composition year"),
    has_strings: Optional[bool] = Query(None, description="Filter to works with/without strings"),
    q: Optional[str] = Query(None, description="Free-text search across title and formula"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    conn = _db()

    conditions = []
    params: list = []

    if composer:
        conditions.append("c.name = ?")
        params.append(composer)

    if instrument:
        if instrument_count is not None:
            conditions.append("""EXISTS (
                SELECT 1 FROM work_instruments wi
                WHERE wi.work_id = w.id
                  AND wi.instrument = ?
                  AND wi.player_count = ?
                  AND wi.is_doubling = 0
            )""")
            params.extend([instrument, instrument_count])
        else:
            conditions.append("""EXISTS (
                SELECT 1 FROM work_instruments wi
                WHERE wi.work_id = w.id AND wi.instrument = ?
            )""")
            params.append(instrument)

    if year_from is not None:
        conditions.append("w.year_start >= ?")
        params.append(year_from)

    if year_to is not None:
        conditions.append("(w.year_start <= ? OR w.year_start IS NULL)")
        params.append(year_to)

    if has_strings is not None:
        conditions.append("w.has_strings = ?")
        params.append(1 if has_strings else 0)

    if q:
        conditions.append("(w.title LIKE ? OR w.formula LIKE ? OR w.slug LIKE ?)")
        term = f"%{q}%"
        params.extend([term, term, term])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    base_sql = f"""
        FROM works w
        JOIN composers c ON c.id = w.composer_id
        {where}
    """

    total = conn.execute(f"SELECT COUNT(*) {base_sql}", params).fetchone()[0]

    offset = (page - 1) * limit
    rows = conn.execute(f"""
        SELECT w.slug, w.title, w.formula, w.year_start, w.year_end,
               w.duration_minutes, w.has_strings, w.catalog,
               c.name AS composer, c.slug AS composer_slug
        {base_sql}
        ORDER BY c.name, w.title
        LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "results": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# /works/{slug}
# ---------------------------------------------------------------------------

@router.get("/works/{slug}", summary="Full detail for a single work")
def get_work(slug: str):
    conn = _db()

    work = conn.execute("""
        SELECT w.*, c.name AS composer_name, c.slug AS composer_slug
        FROM works w
        JOIN composers c ON c.id = w.composer_id
        WHERE w.slug = ?
    """, (slug,)).fetchone()

    if not work:
        raise HTTPException(status_code=404, detail=f"Work not found: {slug!r}")

    instruments = conn.execute("""
        SELECT instrument, family, player_count, is_doubling
        FROM work_instruments
        WHERE work_id = ?
        ORDER BY is_doubling, family, instrument
    """, (work["id"],)).fetchall()

    external_ids = conn.execute("""
        SELECT source, external_id
        FROM work_external_ids
        WHERE work_id = ?
    """, (work["id"],)).fetchall()

    provenance = conn.execute("""
        SELECT source, source_url, confidence, notes
        FROM work_provenance
        WHERE work_id = ?
    """, (work["id"],)).fetchall()

    return {
        **{k: work[k] for k in work.keys() if k not in ("id", "composer_id")},
        "instruments": [dict(r) for r in instruments],
        "external_ids": {r["source"]: r["external_id"] for r in external_ids},
        "provenance": [dict(r) for r in provenance],
    }


# ---------------------------------------------------------------------------
# /instruments/{name}/works
# ---------------------------------------------------------------------------

@router.get("/instruments/{name}/works",
         summary="All works that require a given instrument")
def works_by_instrument(
    name: str,
    include_doublings: bool = Query(False, description="Include works where it only appears as a doubling"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    conn = _db()

    doubling_filter = "" if include_doublings else "AND wi.is_doubling = 0"
    offset = (page - 1) * limit

    total = conn.execute(f"""
        SELECT COUNT(DISTINCT w.id)
        FROM works w
        JOIN work_instruments wi ON wi.work_id = w.id
        WHERE wi.instrument = ? {doubling_filter}
    """, (name,)).fetchone()[0]

    if total == 0:
        raise HTTPException(status_code=404, detail=f"No works found for instrument: {name!r}")

    rows = conn.execute(f"""
        SELECT DISTINCT w.slug, w.title, w.formula, w.year_start,
               c.name AS composer, wi.player_count, wi.is_doubling
        FROM works w
        JOIN composers c ON c.id = w.composer_id
        JOIN work_instruments wi ON wi.work_id = w.id
        WHERE wi.instrument = ? {doubling_filter}
        ORDER BY c.name, w.title
        LIMIT ? OFFSET ?
    """, (name, limit, offset)).fetchall()

    return {
        "instrument": name,
        "total": total,
        "page": page,
        "limit": limit,
        "results": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# /query  — ad-hoc read-only SQL
# ---------------------------------------------------------------------------

class _QueryRequest(BaseModel):
    sql: str
    limit: int = 500


_UNSAFE = {"insert", "update", "delete", "drop", "alter", "create", "replace", "attach"}


@router.post("/query", summary="Run a read-only SQL query against the database")
def run_query(req: _QueryRequest):
    first_word = req.sql.strip().split()[0].lower() if req.sql.strip() else ""
    if first_word in _UNSAFE:
        raise HTTPException(status_code=400, detail=f"Only SELECT queries are allowed (got: {first_word!r})")

    conn = _db()
    try:
        rows = conn.execute(req.sql).fetchmany(req.limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not rows:
        return {"columns": [], "rows": [], "count": 0}

    columns = list(rows[0].keys())
    return {
        "columns": columns,
        "rows": [list(r) for r in rows],
        "count": len(rows),
    }


app.include_router(router)
