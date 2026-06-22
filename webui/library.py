"""Read-side data access for the orchestration database viewer.

This module is the single seam between the web routes and *where the data
actually lives*. Today entries are YAML files in ``data/``; the whole corpus is
small enough to load into memory and filter in Python. When the collection
outgrows that — thousands of works, multiple users, full-text needs — only this
module changes: swap the in-memory index for SQLite / Postgres / a search
engine, keep ``query()`` and ``get()`` returning the same shapes, and neither
the Flask routes nor the frontend need to move.

The query contract is deliberately store-agnostic:

    query(q, composer, source, confidence, valid, sort, page, page_size)
        -> {rows, total, page, page_size, facets}

    get(entry_id) -> {entry, formula, sections} | None
"""
from __future__ import annotations

import os
import threading

import yaml

from instrdb import vocab
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
    """In-memory, lazily-loaded index over ``data/``.

    Thread-safe enough for the Flask dev server; one process, one index.
    Call ``refresh()`` after writing entries to pick up changes.
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._entries: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._loaded = False

    # -- loading --

    def _ensure(self):
        if not self._loaded:
            self.refresh()

    def refresh(self):
        entries: list[dict] = []
        by_id: dict[str, dict] = {}
        for fn in sorted(os.listdir(self.data_dir)):
            if not fn.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(self.data_dir, fn)
            try:
                with open(path) as fh:
                    raw = yaml.safe_load(fh)
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            work = raw.get("work", {}) or {}
            prov = raw.get("provenance", {}) or {}
            problems = validate_entry(raw)
            rec = {
                "file": fn,
                "raw": raw,
                "id": raw.get("id") or fn[:-5],
                "composer": work.get("composer", ""),
                "title": work.get("title", ""),
                "year": work.get("year"),
                "formula": raw.get("formula", ""),
                "source": prov.get("source", ""),
                "confidence": prov.get("confidence", ""),
                "valid": not problems,
                "problems": problems,
            }
            # precomputed lowercase haystack for cheap substring search
            rec["_hay"] = " ".join(str(x).lower() for x in (
                rec["composer"], rec["title"], rec["formula"], rec["id"]))
            entries.append(rec)
            by_id[rec["id"]] = rec
        with self._lock:
            self._entries = entries
            self._by_id = by_id
            self._loaded = True

    # -- read API (store-agnostic contract) --

    def query(self, q="", composer="", source="", confidence="", valid="",
              sort="composer", page=1, page_size=50) -> dict:
        self._ensure()
        rows = self._entries

        q = (q or "").strip().lower()
        if q:
            rows = [r for r in rows if q in r["_hay"]]
        if composer:
            rows = [r for r in rows if r["composer"] == composer]
        if source:
            rows = [r for r in rows if r["source"] == source]
        if confidence:
            rows = [r for r in rows if r["confidence"] == confidence]
        if valid in ("true", "false"):
            want = valid == "true"
            rows = [r for r in rows if r["valid"] == want]

        rows = self._sort(rows, sort)
        total = len(rows)

        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 50), 500))
        start = (page - 1) * page_size
        window = rows[start:start + page_size]

        return {
            "rows": [self._public_row(r) for r in window],
            "total": total,
            "page": page,
            "page_size": page_size,
            "facets": self._facets(),
        }

    def get(self, entry_id: str) -> dict | None:
        self._ensure()
        rec = self._by_id.get(entry_id)
        if not rec:
            return None
        raw = rec["raw"]
        return {
            "entry": raw,
            "formula": raw.get("formula", ""),
            "valid": rec["valid"],
            "problems": rec["problems"],
            "sections": humanize(raw.get("instrumentation", {})),
            "provenance": raw.get("provenance", {}),
        }

    # -- helpers --

    @staticmethod
    def _public_row(r: dict) -> dict:
        return {k: r[k] for k in (
            "id", "composer", "title", "year", "formula",
            "source", "confidence", "valid")}

    @staticmethod
    def _sort(rows, sort):
        key, _, direction = (sort or "composer").partition(":")
        reverse = direction == "desc"
        if key == "title":
            rows = sorted(rows, key=lambda r: r["title"].lower(), reverse=reverse)
        elif key == "year":
            rows = sorted(rows, key=lambda r: (r["year"] is None, r["year"] or 0),
                          reverse=reverse)
        elif key == "formula":
            rows = sorted(rows, key=lambda r: r["formula"], reverse=reverse)
        else:  # composer (default), then title as tiebreak
            rows = sorted(rows, key=lambda r: (r["composer"].lower(),
                                               r["title"].lower()), reverse=reverse)
        return rows

    def _facets(self) -> dict:
        composers: dict[str, int] = {}
        sources: dict[str, int] = {}
        confidences: dict[str, int] = {}
        invalid = 0
        for r in self._entries:
            if r["composer"]:
                composers[r["composer"]] = composers.get(r["composer"], 0) + 1
            if r["source"]:
                sources[r["source"]] = sources.get(r["source"], 0) + 1
            if r["confidence"]:
                confidences[r["confidence"]] = confidences.get(r["confidence"], 0) + 1
            if not r["valid"]:
                invalid += 1
        def _items(d):
            return [{"value": k, "count": v} for k, v in sorted(d.items())]
        return {
            "composers": _items(composers),
            "sources": _items(sources),
            "confidences": _items(confidences),
            "total": len(self._entries),
            "invalid": invalid,
        }
