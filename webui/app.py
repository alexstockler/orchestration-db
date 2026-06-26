#!/usr/bin/env python3
"""Local web UI for the orchestration database.

Run:
    pip install -r requirements.txt
    python webui/app.py
then open http://127.0.0.1:5000

Everything here calls the real `instrdb` package, so the UI and the CLI share one
engine. The Boosey fetch needs internet; parsing/validating/saving work offline.
"""
import io
import os
import re
import sys

import yaml
from flask import Flask, jsonify, render_template, request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from instrdb import Instrumentation, render, parse                # noqa: E402
from instrdb.sources.boosey import parse_scoring                  # noqa: E402
from instrdb.validate import validate_entry                       # noqa: E402
from instrdb.db import get_connection                             # noqa: E402
from webui.library import Library                                 # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
app = Flask(__name__)
library = Library(DATA_DIR)


def slugify(*parts) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", "-".join(p for p in parts if p).lower())
    return s.strip("-")


def dump_yaml(entry) -> str:
    return yaml.safe_dump(entry, allow_unicode=True, sort_keys=False)


def build_entry(composer, title, year, musicid, scoring, duration=None) -> dict:
    parsed = parse_scoring(scoring)
    entry = {
        "id": slugify(composer.split(",")[0] if composer else "", title)
        or f"work-{musicid or 'new'}",
        "work": {"composer": composer or "", "title": title or "",
                 "ids": {"boosey": str(musicid) if musicid else None}},
        "version": {"publisher": "Boosey & Hawkes"},
        "formula": parsed["formula"],
        "instrumentation": parsed["instrumentation"],
        "provenance": {
            "source": "publisher:boosey",
            "confidence": "single_source",
            "notes": "Scoring: " + parsed["scoring_raw"],
        },
    }
    if year:
        entry["work"]["year"] = year
    if musicid:
        entry["provenance"]["source_url"] = (
            f"https://www.boosey.com/pages/cr/catalogue/cat_detail?musicid={musicid}")
    if duration:
        entry["duration_minutes"] = duration
    return entry


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/parse-scoring")
def api_parse_scoring():
    d = request.get_json(force=True)
    entry = build_entry(d.get("composer", ""), d.get("title", ""),
                        d.get("year", ""), d.get("musicid", ""),
                        d.get("scoring", ""))
    return jsonify(ok=True, yaml=dump_yaml(entry), entry=entry)


@app.post("/api/scrape")
def api_scrape():
    """Fetch one or more Boosey musicids and return draft entries."""
    from instrdb.sources.scrape_boosey import fetch, extract_fields
    d = request.get_json(force=True)
    ids = re.findall(r"\d+", d.get("musicids", ""))
    out = []
    for mid in ids:
        try:
            f = extract_fields(fetch(int(mid)))
        except Exception as exc:                      # network / parse failure
            out.append({"musicid": mid, "error": str(exc)})
            continue
        entry = build_entry(f["composer"] or d.get("composer", ""),
                            f["title"], f["year"], mid, f["scoring"],
                            f["duration_minutes"])
        out.append({"musicid": mid, "yaml": dump_yaml(entry),
                    "scoring": f["scoring"]})
    return jsonify(ok=True, results=out)


@app.post("/api/formula-to-struct")
def api_formula_to_struct():
    d = request.get_json(force=True)
    try:
        inst = parse(d.get("formula", ""))
        return jsonify(ok=True,
                       instrumentation=inst.to_obj(),
                       roundtrip=render(inst))
    except Exception as exc:
        return jsonify(ok=False, error=str(exc))


@app.post("/api/struct-to-formula")
def api_struct_to_formula():
    d = request.get_json(force=True)
    try:
        obj = yaml.safe_load(d.get("instrumentation", "")) or {}
        return jsonify(ok=True, formula=render(Instrumentation.from_obj(obj)))
    except Exception as exc:
        return jsonify(ok=False, error=str(exc))


@app.post("/api/save")
def api_save():
    """Validate an edited YAML entry and write it to data/."""
    d = request.get_json(force=True)
    try:
        entry = yaml.safe_load(d.get("yaml", "")) or {}
    except Exception as exc:
        return jsonify(ok=False, problems=[f"YAML parse error: {exc}"])
    problems = validate_entry(entry)
    if problems:
        return jsonify(ok=False, problems=problems)
    eid = entry.get("id") or "untitled"
    path = os.path.join(DATA_DIR, f"{eid}.yaml")
    with open(path, "w") as fh:
        fh.write(dump_yaml(entry))
    library.refresh()
    return jsonify(ok=True, path=os.path.relpath(path, ROOT))


@app.get("/api/list")
def api_list():
    rows = []
    for fn in sorted(os.listdir(DATA_DIR)):
        if not fn.endswith((".yaml", ".yml")):
            continue
        with open(os.path.join(DATA_DIR, fn)) as fh:
            entry = yaml.safe_load(fh)
        problems = validate_entry(entry)
        rows.append({
            "file": fn,
            "title": entry.get("work", {}).get("title", ""),
            "composer": entry.get("work", {}).get("composer", ""),
            "formula": entry.get("formula", ""),
            "confidence": entry.get("provenance", {}).get("confidence", ""),
            "valid": not problems,
            "problems": problems,
        })
    return jsonify(ok=True, rows=rows)


@app.get("/api/library")
def api_library():
    """Server-side search / filter / sort / pagination over the collection."""
    args = request.args
    result = library.query(
        q=args.get("q", ""),
        composer=args.get("composer", ""),
        source=args.get("source", ""),
        confidence=args.get("confidence", ""),
        valid=args.get("valid", ""),
        sort=args.get("sort", "composer"),
        page=args.get("page", 1, type=int),
        page_size=args.get("page_size", 50, type=int),
    )
    return jsonify(ok=True, **result)


@app.get("/api/entry/<entry_id>")
def api_entry(entry_id):
    """Full detail for a single work, with a human-readable breakdown."""
    detail = library.get(entry_id)
    if detail is None:
        return jsonify(ok=False, error="not found"), 404
    return jsonify(ok=True, **detail)


@app.post("/api/refresh")
def api_refresh():
    """Reload the in-memory index from disk (after external edits)."""
    library.refresh()
    return jsonify(ok=True, total=library.query(page_size=1)["total"])


@app.get("/explore")
def explore():
    return render_template("explore.html")


@app.get("/api/explore")
def api_explore():
    """Filterable, paginated work list with pre-computed wind/brass counts."""
    a = request.args
    q           = a.get("q", "").strip()
    composer    = a.get("composer", "").strip()
    min_winds   = a.get("min_winds", type=int)
    max_winds   = a.get("max_winds", type=int)
    min_brass   = a.get("min_brass", type=int)
    max_brass   = a.get("max_brass", type=int)
    has_strings = a.get("has_strings")        # "1", "0", or absent
    has_perc    = a.get("has_perc")           # "1" or absent
    year_from   = a.get("year_from", type=int)
    year_to     = a.get("year_to", type=int)
    sort        = a.get("sort", "composer")
    page        = max(1, a.get("page", 1, type=int))
    page_size   = min(100, max(1, a.get("page_size", 50, type=int)))

    conn = get_connection()

    conds, params = [], []

    if q:
        t = f"%{q.lower()}%"
        conds.append("(LOWER(w.title) LIKE ? OR LOWER(c.name) LIKE ? OR w.formula LIKE ?)")
        params += [t, t, t]
    if composer:
        conds.append("c.name = ?")
        params.append(composer)
    if min_winds is not None:
        conds.append("COALESCE(pc.wind_count,0) >= ?")
        params.append(min_winds)
    if max_winds is not None:
        conds.append("COALESCE(pc.wind_count,0) <= ?")
        params.append(max_winds)
    if min_brass is not None:
        conds.append("COALESCE(pc.brass_count,0) >= ?")
        params.append(min_brass)
    if max_brass is not None:
        conds.append("COALESCE(pc.brass_count,0) <= ?")
        params.append(max_brass)
    if has_strings == "1":
        conds.append("w.has_strings = 1")
    elif has_strings == "0":
        conds.append("w.has_strings = 0")
    if has_perc == "1":
        conds.append("(w.timpani > 0 OR w.perc_players > 0)")
    if year_from is not None:
        conds.append("w.year_start >= ?")
        params.append(year_from)
    if year_to is not None:
        conds.append("(w.year_start IS NULL OR w.year_start <= ?)")
        params.append(year_to)

    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sort_col = {"title": "w.title", "year": "w.year_start",
                "formula": "w.formula"}.get(sort, "c.name")

    sql_base = f"""
        FROM works w
        JOIN composers c ON c.id = w.composer_id
        LEFT JOIN (
            SELECT work_id,
                   SUM(CASE WHEN family='woodwind' AND is_doubling=0 THEN player_count ELSE 0 END) AS wind_count,
                   SUM(CASE WHEN family='brass'    AND is_doubling=0 THEN player_count ELSE 0 END) AS brass_count
            FROM work_instruments GROUP BY work_id
        ) pc ON pc.work_id = w.id
        {where}
    """

    total = conn.execute(f"SELECT COUNT(DISTINCT w.id) {sql_base}", params).fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(f"""
        SELECT DISTINCT w.slug, w.title, w.formula, w.year_start, w.duration_minutes,
               w.has_strings, w.timpani, w.perc_players, w.harp,
               c.name AS composer,
               COALESCE(pc.wind_count,0) AS wind_count,
               COALESCE(pc.brass_count,0) AS brass_count
        {sql_base}
        ORDER BY {sort_col}, w.title
        LIMIT ? OFFSET ?
    """, params + [page_size, offset]).fetchall()

    # Facet: composer list for dropdown
    composers = conn.execute(
        "SELECT c.name, COUNT(w.id) AS n FROM composers c "
        "JOIN works w ON w.composer_id=c.id GROUP BY c.id ORDER BY c.name"
    ).fetchall()

    # Ranges for sliders
    ranges = conn.execute("""
        SELECT
          MAX(COALESCE(pc.wind_count,0))  AS max_winds,
          MAX(COALESCE(pc.brass_count,0)) AS max_brass,
          MIN(w.year_start) AS min_year,
          MAX(w.year_start) AS max_year
        FROM works w
        LEFT JOIN (
            SELECT work_id,
                   SUM(CASE WHEN family='woodwind' AND is_doubling=0 THEN player_count ELSE 0 END) AS wind_count,
                   SUM(CASE WHEN family='brass'    AND is_doubling=0 THEN player_count ELSE 0 END) AS brass_count
            FROM work_instruments GROUP BY work_id
        ) pc ON pc.work_id = w.id
    """).fetchone()

    return jsonify(
        total=total, page=page, page_size=page_size,
        rows=[dict(r) for r in rows],
        composers=[{"name": r[0], "count": r[1]} for r in composers],
        ranges=dict(ranges),
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
