"""Public HTML routes — no API key required.

These routes query the database directly and render Jinja2 templates.
The JSON API routes in main.py are unchanged and remain key-protected.
"""
from __future__ import annotations

import sqlite3
import urllib.parse
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from instrdb.db import DB_PATH, get_connection

web = APIRouter()

_templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Custom filter: URL-encode a single value for use in query strings
_templates.env.filters["qenc"] = lambda v: urllib.parse.quote_plus(str(v))

# Confidence tier ranking for consistent ordering
_CONF_RANK = """CASE confidence
    WHEN 'score_verified' THEN 4
    WHEN 'multi_source'   THEN 3
    WHEN 'single_source'  THEN 2
    WHEN 'unverified'     THEN 1
    ELSE 0 END"""

_UNSAFE = {"insert", "update", "delete", "drop", "alter", "create", "replace", "attach"}


def _db() -> sqlite3.Connection:
    return get_connection(DB_PATH)


def _best_confidence_subquery() -> str:
    return f"""(
        SELECT confidence FROM work_provenance
        WHERE work_id = w.id
        ORDER BY {_CONF_RANK} DESC
        LIMIT 1
    ) AS confidence"""


def _all_composers(conn: sqlite3.Connection) -> list[str]:
    return [r["name"] for r in conn.execute("SELECT name FROM composers ORDER BY name").fetchall()]


def _all_instruments(conn: sqlite3.Connection) -> list[str]:
    return [
        r["instrument"]
        for r in conn.execute(
            "SELECT DISTINCT instrument FROM work_instruments WHERE is_doubling=0 ORDER BY instrument"
        ).fetchall()
    ]


# ---------------------------------------------------------------------------
# Homepage / search
# ---------------------------------------------------------------------------

@web.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    q: Optional[str] = None,
    composer: Optional[str] = None,
    instrument: Optional[str] = None,
    page: int = 1,
):
    conn = _db()
    composers = _all_composers(conn)
    instruments = _all_instruments(conn)

    results = None
    total = 0
    limit = 50

    if any([q, composer, instrument]):
        conditions: list[str] = []
        params: list = []

        if composer:
            conditions.append("c.name = ?")
            params.append(composer)

        if instrument:
            conditions.append("""EXISTS (
                SELECT 1 FROM work_instruments wi
                WHERE wi.work_id = w.id AND wi.instrument = ? AND wi.is_doubling = 0
            )""")
            params.append(instrument)

        if q:
            conditions.append("(w.title LIKE ? OR w.formula LIKE ?)")
            term = f"%{q}%"
            params.extend([term, term])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total = conn.execute(
            f"SELECT COUNT(*) FROM works w JOIN composers c ON c.id = w.composer_id {where}",
            params,
        ).fetchone()[0]

        offset = (page - 1) * limit
        rows = conn.execute(f"""
            SELECT w.slug, w.title, w.formula, w.year_start, w.catalog,
                   c.name AS composer,
                   {_best_confidence_subquery()}
            FROM works w
            JOIN composers c ON c.id = w.composer_id
            {where}
            ORDER BY c.name, w.title
            LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()

        results = [dict(r) for r in rows]

    # Build base query string for pagination links (without page=)
    base_qs_parts: dict[str, str] = {}
    if q:
        base_qs_parts["q"] = q
    if composer:
        base_qs_parts["composer"] = composer
    if instrument:
        base_qs_parts["instrument"] = instrument
    base_qs = urllib.parse.urlencode(base_qs_parts)

    return _templates.TemplateResponse(request, "index.html", {
        "composers": composers,
        "instruments": instruments,
        "results": results,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
        "q": q or "",
        "selected_composer": composer or "",
        "selected_instrument": instrument or "",
        "base_qs": base_qs,
    })


# ---------------------------------------------------------------------------
# Composer index
# ---------------------------------------------------------------------------

@web.get("/browse/composers", response_class=HTMLResponse)
def composers_page(request: Request):
    conn = _db()
    rows = conn.execute("""
        SELECT c.name, c.slug, COUNT(w.id) AS work_count
        FROM composers c
        JOIN works w ON w.composer_id = c.id
        GROUP BY c.id
        ORDER BY c.name
    """).fetchall()
    return _templates.TemplateResponse(request, "composers.html", {
        "composers": [dict(r) for r in rows],
    })


# ---------------------------------------------------------------------------
# Work detail
# ---------------------------------------------------------------------------

@web.get("/browse/works/{slug}", response_class=HTMLResponse)
def work_detail(request: Request, slug: str):
    conn = _db()

    work = conn.execute("""
        SELECT w.*, c.name AS composer_name, c.slug AS composer_slug
        FROM works w
        JOIN composers c ON c.id = w.composer_id
        WHERE w.slug = ?
    """, (slug,)).fetchone()

    if not work:
        return _templates.TemplateResponse(request, "404.html", {}, status_code=404)

    work = dict(work)

    instruments = conn.execute("""
        SELECT instrument, family, player_count, is_doubling
        FROM work_instruments
        WHERE work_id = ?
        ORDER BY is_doubling, family, instrument
    """, (work["id"],)).fetchall()

    provenance = conn.execute(f"""
        SELECT source, source_url, confidence, notes
        FROM work_provenance
        WHERE work_id = ?
        ORDER BY {_CONF_RANK} DESC
    """, (work["id"],)).fetchall()

    external_ids = conn.execute(
        "SELECT source, external_id FROM work_external_ids WHERE work_id = ?",
        (work["id"],),
    ).fetchall()

    best_confidence = provenance[0]["confidence"] if provenance else None

    return _templates.TemplateResponse(request, "work_detail.html", {
        "work": work,
        "instruments": [dict(r) for r in instruments],
        "provenance": [dict(r) for r in provenance],
        "external_ids": {r["source"]: r["external_id"] for r in external_ids},
        "best_confidence": best_confidence,
        "composer_qs": urllib.parse.urlencode({"composer": work["composer_name"]}),
    })


# ---------------------------------------------------------------------------
# SQL explorer
# ---------------------------------------------------------------------------

@web.get("/explore", response_class=HTMLResponse)
def explore_get(request: Request):
    default_sql = (
        "SELECT c.name AS composer, COUNT(w.id) AS works\n"
        "FROM composers c\n"
        "JOIN works w ON w.composer_id = c.id\n"
        "GROUP BY c.name\n"
        "ORDER BY works DESC"
    )
    return _templates.TemplateResponse(request, "explore.html", {
        "sql": default_sql,
        "results": None,
        "error": None,
    })


@web.post("/explore", response_class=HTMLResponse)
async def explore_post(
    request: Request,
    sql: str = Form(...),
    limit: int = Form(500),
):
    first_word = sql.strip().split()[0].lower() if sql.strip() else ""
    error = None
    results = None

    if first_word in _UNSAFE:
        error = f"Only SELECT queries are allowed (got: {first_word!r})"
    else:
        conn = _db()
        try:
            rows = conn.execute(sql).fetchmany(min(limit, 2000))
            columns = list(rows[0].keys()) if rows else []
            results = {
                "columns": columns,
                "rows": [list(r) for r in rows],
                "count": len(rows),
            }
        except Exception as exc:
            error = str(exc)

    return _templates.TemplateResponse(request, "explore.html", {
        "sql": sql,
        "results": results,
        "error": error,
    })
