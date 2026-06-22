#!/usr/bin/env python3
"""Fetch IMSLP work pages via the MediaWiki API and emit schema entries.

Usage:
    # Fetch a batch of known IMSLP page titles:
    python -m instrdb.sources.scrape_imslp \
        "Symphony No. 5 (Beethoven, Ludwig van)" \
        "Symphony No. 9 (Beethoven, Ludwig van)"

    # Fetch a whole composer's category:
    python -m instrdb.sources.scrape_imslp --composer "Beethoven, Ludwig van"

    # Fetch from a file of page titles (one per line):
    python -m instrdb.sources.scrape_imslp --file titles.txt

    # Dry-run: print parsed result without writing files
    python -m instrdb.sources.scrape_imslp --dry-run "Symphony No. 5 (Beethoven, Ludwig van)"

Output goes to data/<slug>.yaml. Already-present files are skipped unless
--force is given. Unrecognised instrumentation fragments are written to
additional_raw and also logged to stderr for review.

Be polite: requests are throttled to ~1/s and responses are cached in
.imslp_cache/ so re-runs don't re-hit the server.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from .parse_imslp_scoring import parse_imslp_scoring

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

API = "https://imslp.org/api.php"
UA = "orchestration-db/0.1 (open instrumentation database; https://github.com/alexstockler/orchestration-db)"
CACHE_DIR = Path(".imslp_cache")
RATE_LIMIT_S = 1.2   # seconds between requests


def _cache_path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", key)[:180]
    return CACHE_DIR / (safe + ".json")


def _fetch_api(params: dict) -> dict:
    """Hit the MediaWiki API with caching. Returns decoded JSON."""
    cache_key = urllib.parse.urlencode(sorted(params.items()))
    cp = _cache_path(cache_key)
    if cp.exists():
        return json.loads(cp.read_text())
    CACHE_DIR.mkdir(exist_ok=True)
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    time.sleep(RATE_LIMIT_S)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    cp.write_text(json.dumps(data))
    return data


# ---------------------------------------------------------------------------
# IMSLP page parsing
# ---------------------------------------------------------------------------

def _get_page_wikitext(title: str) -> str | None:
    """Return the raw wikitext for an IMSLP page, or None if not found."""
    data = _fetch_api({
        "action": "query",
        "titles": title,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
    })
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        if "missing" in page:
            return None
        slots = page.get("revisions", [{}])[0].get("slots", {})
        return slots.get("main", {}).get("*", "")
    return None


def _extract_infobox_field(wikitext: str, field: str) -> str:
    """Extract a field value from an IMSLP infobox template."""
    pattern = re.compile(
        r"\|\s*" + re.escape(field) + r"\s*=\s*(.*?)(?=\n\s*\||\n\s*\}\})",
        re.S | re.I,
    )
    m = pattern.search(wikitext)
    if not m:
        return ""
    raw = m.group(1).strip()
    # Strip wiki markup: [[links]], {{templates}}, <tags>
    raw = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", raw)
    raw = re.sub(r"\{\{[^}]*\}\}", "", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"'''?", "", raw)
    return " ".join(raw.split())


def _extract_work_fields(wikitext: str) -> dict:
    """Pull title, composer, opus, key, year, instrumentation from wikitext."""
    return {
        "title": _extract_infobox_field(wikitext, "Work Title"),
        "composer": _extract_infobox_field(wikitext, "Composer"),
        "opus": _extract_infobox_field(wikitext, "Opus/Catalogue Number/Key"),
        "key": _extract_infobox_field(wikitext, "Key"),
        "year": _extract_infobox_field(wikitext, "Year/Date of Composition"),
        "instrumentation": _extract_infobox_field(wikitext, "Instrumentation"),
        "movements": _extract_infobox_field(wikitext, "Movements/Sections"),
        "duration": _extract_infobox_field(wikitext, "Average Duration"),
        "imslp_id": _extract_infobox_field(wikitext, "IMSLP Page Name"),
        "wikidata": _extract_infobox_field(wikitext, "Wikidata"),
    }


# ---------------------------------------------------------------------------
# IMSLP category enumeration
# ---------------------------------------------------------------------------

def _list_composer_works(composer_name: str) -> list[str]:
    """Return IMSLP page titles for orchestral works by a composer.

    Uses the IMSLP Special:Search / categorymembers API to find works in
    the composer's main category. All sub-pages are returned; the caller
    should filter by instrumentation after fetching.
    """
    # IMSLP composer categories follow "Category:Surname, Firstname"
    category = f"Category:{composer_name}"
    titles = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": "500",
            "cmtype": "page",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = _fetch_api(params)
        members = data.get("query", {}).get("categorymembers", [])
        titles.extend(m["title"] for m in members)
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    return titles


# ---------------------------------------------------------------------------
# Slug / entry building
# ---------------------------------------------------------------------------

def _slugify(composer: str, title: str) -> str:
    # "Beethoven, Ludwig van" -> "beethoven"
    last = composer.split(",")[0].strip().lower() if "," in composer else composer.lower()
    base = f"{last}-{title}".lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    return base.strip("-")[:80]


def _parse_year(raw: str) -> int | None:
    m = re.search(r"\b(1[5-9]\d\d|20[012]\d)\b", raw)
    return int(m.group(1)) if m else None


def _parse_duration(raw: str) -> int | None:
    m = re.search(r"(\d+)\s*(?:min|'|minutes?)", raw, re.I)
    return int(m.group(1)) if m else None


def _imslp_page_url(title: str) -> str:
    return "https://imslp.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def build_entry(page_title: str) -> dict | None:
    """Fetch an IMSLP work page and return a validated entry dict, or None."""
    wikitext = _get_page_wikitext(page_title)
    if not wikitext:
        print(f"  [skip] page not found: {page_title!r}", file=sys.stderr)
        return None

    fields = _extract_work_fields(wikitext)
    scoring_text = fields["instrumentation"]

    if not scoring_text:
        print(f"  [skip] no instrumentation field: {page_title!r}", file=sys.stderr)
        return None

    parsed = parse_imslp_scoring(scoring_text)

    if parsed["unrecognised"]:
        print(f"  [review] {page_title!r} has unrecognised fragments:", file=sys.stderr)
        for frag in parsed["unrecognised"]:
            print(f"           {frag!r}", file=sys.stderr)

    composer = fields["composer"] or page_title.split("(")[-1].rstrip(")")
    title = fields["title"] or page_title.split("(")[0].strip()

    ids: dict = {"imslp": page_title}
    if fields["wikidata"]:
        ids["wikidata"] = fields["wikidata"]

    entry: dict = {
        "id": _slugify(composer, title),
        "work": {
            "composer": composer,
            "title": title,
            "ids": ids,
        },
        "formula": parsed["formula"],
        "instrumentation": parsed["instrumentation"],
        "provenance": {
            "source": "imslp",
            "source_url": _imslp_page_url(page_title),
            "confidence": "single_source",
            "notes": "Instrumentation: " + scoring_text,
        },
    }

    if fields["opus"]:
        entry["work"]["catalog"] = fields["opus"]
    year = _parse_year(fields["year"])
    if year:
        entry["work"]["year"] = year
    dur = _parse_duration(fields["duration"])
    if dur:
        entry["duration_minutes"] = dur

    return entry


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_entry(entry: dict, out_dir: Path, force: bool = False) -> bool:
    path = out_dir / f"{entry['id']}.yaml"
    if path.exists() and not force:
        print(f"  [skip] already exists: {path}", file=sys.stderr)
        return False
    path.write_text(
        yaml.safe_dump(entry, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return True


def main():
    ap = argparse.ArgumentParser(description="Scrape IMSLP instrumentation data")
    ap.add_argument("titles", nargs="*", help="IMSLP page title(s)")
    ap.add_argument("--composer", help="Fetch all works for a composer category")
    ap.add_argument("--file", help="File of page titles, one per line")
    ap.add_argument("--out-dir", default="data", help="Output directory (default: data/)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing files")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and print without writing files")
    args = ap.parse_args()

    titles: list[str] = list(args.titles)

    if args.file:
        titles += [l.strip() for l in Path(args.file).read_text().splitlines()
                   if l.strip() and not l.startswith("#")]

    if args.composer:
        print(f"Enumerating works for {args.composer!r}...", file=sys.stderr)
        titles += _list_composer_works(args.composer)

    if not titles:
        ap.print_help()
        sys.exit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)

    ok = skip = fail = 0
    for title in titles:
        print(f"Fetching: {title}", file=sys.stderr)
        try:
            entry = build_entry(title)
        except Exception as exc:
            print(f"  [error] {exc}", file=sys.stderr)
            fail += 1
            continue
        if entry is None:
            skip += 1
            continue
        if args.dry_run:
            print(yaml.safe_dump(entry, allow_unicode=True, sort_keys=False))
            ok += 1
        else:
            wrote = _write_entry(entry, out_dir, force=args.force)
            if wrote:
                print(f"  wrote: {out_dir}/{entry['id']}.yaml")
                ok += 1
            else:
                skip += 1

    print(f"\nDone: {ok} written, {skip} skipped, {fail} errors.", file=sys.stderr)


if __name__ == "__main__":
    main()
