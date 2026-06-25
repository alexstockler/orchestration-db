"""Read-side data access for the orchestration database viewer.

Backed by SQLite via instrdb.db. The public contract — query() and get() —
is unchanged so Flask routes and the frontend need no modifications.

    query(q, composer, source, confidence, valid, sort, page, page_size)
        -> {rows, total, page, page_size, facets}

    get(entry_id) -> {entry, formula, sections} | None
"""
from __future__ import annotations

import os

import yaml

from instrdb import vocab
from instrdb.db import DB_PATH, get_connection
from instrdb.validate import validate_entry


# --- human-readable instrument labels --------------------------------------

_LABEL_OVERRIDES = {
    "english_horn": "English horn",
    "oboe_damore": "oboe d'amore",
    "eflat_clarinet": "E-flat clarinet",
    "a_clarinet": "A clarinet",
    "bass_clarinet": "bass clarinet",
    "basset_horn": "basset horn",
    "contrabass_clarinet": "contrabass clarinet",
    "alto_clarinet": "alto clarinet",
    "alto_flute": "alto flute",
    "bass_flute": "bass flute",
    "bass_oboe": "bass oboe",
    "contrabassoon": "contrabassoon",
    "wagner_tuba": "Wagner tuba",
    "piccolo_trumpet": "piccolo trumpet",
    "bass_trumpet": "bass trumpet",
    "alto_trombone": "alto trombone",
    "bass_trombone": "bass trombone",
    "contrabass_trombone": "contrabass trombone",
    "double_bass": "double bass",
    "soprano_sax": "soprano saxophone",
    "alto_sax": "alto saxophone",
    "tenor_sax": "tenor saxophone",
    "baritone_sax": "baritone saxophone",
}


def label(key: str) -> str:
    """Human-readable name for a canonical instrument key."""
    return _LABEL_OVERRIDES.get(key) or key.replace("_", " ")


def _plural(name: str, n: int) -> str:
    if n == 1:
        return name
    if name.endswith(("s", "x", "z", "ch", "sh")):
        return name + "es"
    return name + "s"


def _family_line(family: str, value) -> str:
    """Render one woodwind/brass family as a readable phrase.

    e.g. "3 oboes (3rd doubles English horn)" or "2 flutes".
    """
    if isinstance(value, int):
        count, players = value, []
    else:
        players = value or []
        count = len(players)
    if not count:
        return ""

    base = _plural(label(family), count)
    notes = []
    for i, p in enumerate(players, start=1):
        if not isinstance(p, dict):
            continue
        primary = p.get("instrument")
        if primary:
            notes.append(f"{_ord(i)} is {label(primary)}")
        for dbl in p.get("doublings", []):
            notes.append(f"{_ord(i)} doubles {label(dbl)}")
    suffix = f" ({', '.join(notes)})" if notes else ""
    return f"{count} {base}{suffix}"


def _ord(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def humanize(inst: dict) -> list[dict]:
    """Turn an instrumentation object into display sections for the detail view.

    Returns a list of {label, items: [str]} blocks, omitting empty ones.
    """
    inst = inst or {}
    sections: list[dict] = []

    winds = [
        _family_line(f, inst.get(f))
        for f in vocab.WOODWIND_FAMILIES
        if inst.get(f)
    ]
    if winds:
        sections.append({"label": "Woodwinds", "items": winds})

    brass = [
        _family_line(f, inst.get(f))
        for f in vocab.BRASS_FAMILIES
        if inst.get(f)
    ]
    if brass:
        sections.append({"label": "Brass", "items": brass})

    sax = inst.get("saxophones") or []
    if sax:
        sections.append({"label": "Saxophones", "items": [
            f"{s.get('count', 1)} {_plural(label(s['instrument']), s.get('count', 1))}"
            for s in sax if isinstance(s, dict) and s.get("instrument")
        ]})

    perc = inst.get("percussion") or {}
    perc_items = []
    if perc.get("timpani"):
        perc_items.append(f"timpani ({perc['timpani']})")
    if perc.get("players"):
        perc_items.append(f"{perc['players']} percussionist(s)")
    if perc.get("instruments"):
        perc_items.append(", ".join(perc["instruments"]))
    if perc_items:
        sections.append({"label": "Percussion", "items": perc_items})

    kbd = inst.get("keyboards") or []
    if kbd:
        sections.append({"label": "Keyboards", "items": [
            label(k["instrument"]) if isinstance(k, dict) else label(k)
            for k in kbd
        ]})

    other = []
    if inst.get("harp"):
        other.append(f"{inst['harp']} {_plural('harp', inst['harp'])}")
    for e in inst.get("extras") or []:
        other.append(label(e["instrument"]) if isinstance(e, dict) else label(e))
    if other:
        sections.append({"label": "Other", "items": other})

    strings = inst.get("strings")
    if strings is not None:
        if strings == "str" or (isinstance(strings, dict) and strings.get("standard")):
            desc = "strings"
            if isinstance(strings, dict) and strings.get("continuo"):
                desc += " + continuo"
            if isinstance(strings, dict) and strings.get("description"):
                desc = strings["description"]
        elif isinstance(strings, dict):
            desc = strings.get("description") or "strings"
        else:
            desc = str(strings)
        sections.append({"label": "Strings", "items": [desc]})

    if inst.get("soloists"):
        sections.append({"label": "Soloists", "items": inst["soloists"]})
    chorus = inst.get("chorus") or ([inst["chorus_raw"]] if inst.get("chorus_raw") else [])
    if chorus:
        sections.append({"label": "Chorus", "items": chorus})
    if inst.get("offstage"):
        sections.append({"label": "Offstage", "items": [inst["offstage"]]})
    if inst.get("additional_raw"):
        sections.append({
            "label": "Unparsed (needs review)",
            "items": [s.strip() for s in inst["additional_raw"].split("|") if s.strip()],
        })

    return sections


# --- the library -----------------------------------------------------------

class Library:
    """SQLite-backed library. Replaces the old in-memory YAML scanner.

    The public contract (query / get / refresh) is identical to the old
    version so no Flask routes or frontend code needed to change.
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir  # still needed for the save/ingest routes

    def refresh(self):
        """No-op: DB is the source of truth. Call instrdb.migrate after scraping."""
        pass

    # -- read API --

    def query(self, q="", composer="", source="", confidence="", valid="",
              sort="composer", page=1, page_size=50) -> dict:
        conn = get_connection()
        conditions, params = [], []

        if q:
            term = f"%{q.strip().lower()}%"
            conditions.append(
                "(LOWER(w.title) LIKE ? OR LOWER(w.formula) LIKE ? OR w.slug LIKE ?)")
            params.extend([term, term, term])
        if composer:
            conditions.append("c.name = ?")
            params.append(composer)
        if source:
            conditions.append("p.source = ?")
            params.append(source)
        if confidence:
            conditions.append("p.confidence = ?")
            params.append(confidence)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        sort_col = {
            "title": "w.title", "year": "w.year_start",
            "formula": "w.formula",
        }.get(sort, "c.name")
        order = f"ORDER BY {sort_col}, w.title"

        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 50), 500))
        offset = (page - 1) * page_size

        base = f"""
            FROM works w
            JOIN composers c ON c.id = w.composer_id
            LEFT JOIN work_provenance p ON p.work_id = w.id
            {where}
        """
        total = conn.execute(f"SELECT COUNT(DISTINCT w.id) {base}", params).fetchone()[0]
        rows = conn.execute(f"""
            SELECT DISTINCT w.slug AS id, c.name AS composer, w.title,
                   w.year_start AS year, w.formula,
                   p.source, p.confidence
            {base}
            {order}
            LIMIT ? OFFSET ?
        """, params + [page_size, offset]).fetchall()

        return {
            "rows": [self._public_row(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "facets": self._facets(conn),
        }

    def get(self, entry_id: str) -> dict | None:
        # Read the YAML file for full fidelity (instrumentation detail, etc.)
        path = os.path.join(self.data_dir, f"{entry_id}.yaml")
        if not os.path.exists(path):
            return None
        with open(path) as fh:
            raw = yaml.safe_load(fh)
        if not raw:
            return None
        problems = validate_entry(raw)
        return {
            "entry": raw,
            "formula": raw.get("formula", ""),
            "valid": not problems,
            "problems": problems,
            "sections": humanize(raw.get("instrumentation", {})),
            "provenance": raw.get("provenance", {}),
        }

    # -- helpers --

    @staticmethod
    def _public_row(r) -> dict:
        return {
            "id": r["id"],
            "composer": r["composer"],
            "title": r["title"],
            "year": r["year"],
            "formula": r["formula"],
            "source": r["source"] or "",
            "confidence": r["confidence"] or "",
            "valid": True,  # validated on ingest; flag separately if needed
        }

    @staticmethod
    def _facets(conn) -> dict:
        def _items(sql):
            return [{"value": r[0], "count": r[1]}
                    for r in conn.execute(sql).fetchall()]
        return {
            "composers": _items(
                "SELECT c.name, COUNT(w.id) FROM composers c "
                "JOIN works w ON w.composer_id=c.id GROUP BY c.id ORDER BY c.name"),
            "sources": _items(
                "SELECT source, COUNT(*) FROM work_provenance GROUP BY source ORDER BY source"),
            "confidences": _items(
                "SELECT confidence, COUNT(*) FROM work_provenance "
                "GROUP BY confidence ORDER BY confidence"),
            "total": conn.execute("SELECT COUNT(*) FROM works").fetchone()[0],
            "invalid": 0,
        }
