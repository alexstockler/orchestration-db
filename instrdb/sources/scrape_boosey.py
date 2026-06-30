#!/usr/bin/env python3
"""Boosey & Hawkes catalogue scraper.

Two-phase approach:
  1. Enumerate: Wikidata SPARQL → collect Boosey musicids via P856 website URLs.
  2. Fetch: plain HTTP to each cat_detail page.

Usage:
    # Fetch all works for a composer (auto-looks up Wikidata QID):
    python -m instrdb.sources.scrape_boosey --composer "Britten, Benjamin"

    # Supply the QID explicitly to skip the name lookup:
    python -m instrdb.sources.scrape_boosey --composer "Britten, Benjamin" --qid Q7315

    # Fetch specific musicids directly:
    python -m instrdb.sources.scrape_boosey 6803 6144

    # Dry-run — parse and print without writing:
    python -m instrdb.sources.scrape_boosey --dry-run 6803

Output goes to data/<slug>.yaml. Existing files are skipped unless --force.
Detail pages are cached in .boosey_cache/ to avoid re-fetching.
Instrumentation is factual and not copyright-protectable; catalogue
compilation belongs to Boosey & Hawkes — use this only for research.

robots.txt: /form/, /publishing/, /webservices/ are disallowed;
            catalogue pages are not listed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from .boosey import parse_scoring

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DETAIL_URL     = "https://www.boosey.com/pages/cr/catalogue/cat_detail?musicid={}"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Browser-like UA for Boosey (plain-text bots are often blocked)
UA_BOOSEY = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 orchestration-db/0.1"
)
# Transparent UA for Wikidata
UA_WIKIDATA = (
    "orchestration-db/0.1 (open instrumentation database; "
    "https://github.com/alexstockler/orchestration-db)"
)

CACHE_DIR   = Path(".boosey_cache")
_MIN_DELAY  = 0.5   # 2 req/s — polite for a publisher site
_MAX_DELAY  = 30.0
_current_delay = _MIN_DELAY


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", key)[:180]
    return CACHE_DIR / (safe + ".html")


def _fetch_detail_html(musicid: int) -> str:
    """Fetch a cat_detail page, using disk cache to avoid re-fetching."""
    global _current_delay
    cp = _cache_path(f"musicid_{musicid}")
    if cp.exists():
        return cp.read_text(encoding="utf-8")

    CACHE_DIR.mkdir(exist_ok=True)
    url = DETAIL_URL.format(musicid)
    req = urllib.request.Request(url, headers={"User-Agent": UA_BOOSEY})

    for attempt in range(5):
        time.sleep(_current_delay)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", "replace")
            cp.write_text(html, encoding="utf-8")
            _current_delay = _MIN_DELAY
            return html
        except Exception as exc:
            _current_delay = min(_current_delay * 2, _MAX_DELAY)
            print(
                f"  [warn] fetch failed for musicid={musicid} (attempt {attempt + 1}/5): {exc};"
                f" backing off to {_current_delay:.1f}s",
                file=sys.stderr,
            )
            if attempt == 4:
                raise


# ---------------------------------------------------------------------------
# Detail page parsing
# ---------------------------------------------------------------------------

def _extract_fields(html: str, musicid: int) -> dict:
    """Extract structured fields from a Boosey detail page."""
    # Title
    title = ""
    mh1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if mh1:
        title = re.sub(r"<[^>]+>", "", mh1.group(1)).strip()

    # Composer — extract from the single /composer/<name> href in the page,
    # then look up the display name (Lastname, Firstname) from the select dropdown.
    composer = ""
    mc = re.search(r'href=["\']?(/composer/[^"\'>\s]+)', html)
    if mc:
        path = mc.group(1)
        # Try the select option which has "Lastname, Firstname" display text
        opt = re.search(
            r'<option value="' + re.escape(path) + r'"[^>]*>\s*([^<]+?)\s*</option>',
            html,
        )
        if opt:
            composer = opt.group(1).strip()
        else:
            # Fall back to URL-decoding the path segment
            composer = urllib.parse.unquote_plus(path.split("/composer/")[-1])

    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

    myear  = re.search(r"\((\d{4}(?:[-/]\d{2,4})?)\)", text)
    dur    = re.search(r"Duration:\s*([0-9]+)['’]", text)
    scoring = re.search(
        r"Scoring\s+(.*?)\s+(?:Abbreviations|Publisher|Opera|Programme|Repertoire)",
        text,
    )

    return {
        "musicid":          musicid,
        "title":            title,
        "composer":         composer,
        "year":             myear.group(1) if myear else None,
        "duration_minutes": int(dur.group(1)) if dur else None,
        "scoring":          scoring.group(1).strip() if scoring else "",
    }


# ---------------------------------------------------------------------------
# Slug / entry building
# ---------------------------------------------------------------------------

def _slugify(composer: str, title: str) -> str:
    def _ascii(s: str) -> str:
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

    last = composer.split(",")[0].strip() if "," in composer else composer
    base = f"{_ascii(last)}-{_ascii(title)}".lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    return base.strip("-")[:80]


def _parse_year(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r"\b(1[5-9]\d\d|20[012]\d)\b", raw)
    return int(m.group(1)) if m else None


def build_entry(musicid: int) -> dict | None:
    """Fetch a Boosey work page and return a validated entry dict, or None."""
    try:
        html   = _fetch_detail_html(musicid)
    except Exception as exc:
        print(f"  [error] failed to fetch musicid={musicid}: {exc}", file=sys.stderr)
        return None

    fields = _extract_fields(html, musicid)

    if not fields["scoring"]:
        print(f"  [skip] no scoring block: musicid={musicid} {fields['title']!r}", file=sys.stderr)
        return None

    parsed   = parse_scoring(fields["scoring"])
    composer = fields["composer"]
    title    = fields["title"]

    if not composer or not title:
        print(f"  [skip] missing composer/title: musicid={musicid}", file=sys.stderr)
        return None

    entry: dict = {
        "id": _slugify(composer, title),
        "work": {
            "composer": composer,
            "title":    title,
            "ids":      {"boosey": str(musicid)},
        },
        "formula":         parsed["formula"],
        "instrumentation": parsed["instrumentation"],
        "provenance": {
            "source":      "publisher:boosey",
            "source_url":  DETAIL_URL.format(musicid),
            "confidence":  "single_source",
            "notes":       "Scoring: " + fields["scoring"],
        },
    }

    year = _parse_year(fields["year"])
    if year:
        entry["work"]["year"] = year
    if fields["duration_minutes"]:
        entry["duration_minutes"] = fields["duration_minutes"]

    return entry


# ---------------------------------------------------------------------------
# Wikidata SPARQL enumeration
# ---------------------------------------------------------------------------

def _sparql_query(query: str) -> list[dict]:
    """Run a SPARQL query against Wikidata and return the bindings list."""
    import urllib.error
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    url = f"{WIKIDATA_SPARQL}?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_WIKIDATA,
        "Accept": "application/sparql-results+json",
    })
    delay = 2.0
    for attempt in range(5):
        time.sleep(delay)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            return data.get("results", {}).get("bindings", [])
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = int(exc.headers.get("Retry-After", delay * 2))
                print(f"  [warn] Wikidata rate-limited; waiting {retry_after}s…", file=sys.stderr)
                delay = min(retry_after, 120)
            else:
                raise
    raise RuntimeError("Wikidata SPARQL rate-limit exceeded after 5 retries")


def _qid_from_uri(uri: str) -> str | None:
    m = re.search(r"/(Q\d+)$", uri)
    return m.group(1) if m else None


def lookup_composer_qid(composer_name: str) -> str | None:
    """Find a composer's Wikidata QID by name ("Lastname, Firstname")."""
    parts = [p.strip() for p in composer_name.split(",", 1)]
    label = f"{parts[1]} {parts[0]}" if len(parts) == 2 else parts[0]

    query = f"""
    SELECT ?composer WHERE {{
      ?composer wdt:P31 wd:Q5 ;
                rdfs:label "{label}"@en .
    }}
    LIMIT 1
    """
    bindings = _sparql_query(query)
    if not bindings:
        return None
    return _qid_from_uri(bindings[0].get("composer", {}).get("value", ""))


def list_composer_works(composer_name: str, qid: str | None = None) -> list[int]:
    """Enumerate Boosey musicids for a composer via Wikidata SPARQL.

    Queries for works by the composer that have an official website (P856)
    pointing to boosey.com, then extracts musicid from the URL.

    Falls back to works with publisher=Boosey & Hawkes (P123=Q1249726) that
    also have a Boosey URL via P856 on the work itself.
    """
    if not qid:
        print(f"Looking up Wikidata QID for {composer_name!r}…", file=sys.stderr)
        qid = lookup_composer_qid(composer_name)
        if not qid:
            print(
                f"  [error] Could not find Wikidata QID for {composer_name!r}.\n"
                f"  Pass --qid Q<number> to specify it directly.\n"
                f"  Find it at: https://www.wikidata.org/w/index.php?search={urllib.parse.quote(composer_name)}",
                file=sys.stderr,
            )
            return []
        print(f"  QID: {qid}", file=sys.stderr)

    # Primary: works with a boosey.com P856 URL
    query = f"""
    SELECT DISTINCT ?url WHERE {{
      ?work wdt:P86 wd:{qid} ;
            wdt:P856 ?url .
      FILTER(CONTAINS(STR(?url), "boosey.com"))
    }}
    """
    musicids: set[int] = set()
    for binding in _sparql_query(query):
        href = binding.get("url", {}).get("value", "")
        m = re.search(r"musicid=(\d+)", href)
        if m:
            musicids.add(int(m.group(1)))

    # Secondary: works where the composer is listed but the Boosey URL is on
    # a different statement (e.g. via the work's sitelinks or P953)
    if not musicids:
        query2 = f"""
        SELECT DISTINCT ?url WHERE {{
          ?work wdt:P86 wd:{qid} ;
                wdt:P953 ?url .
          FILTER(CONTAINS(STR(?url), "boosey.com"))
        }}
        """
        for binding in _sparql_query(query2):
            href = binding.get("url", {}).get("value", "")
            m = re.search(r"musicid=(\d+)", href)
            if m:
                musicids.add(int(m.group(1)))

    print(
        f"  Found {len(musicids)} Boosey musicid(s) via Wikidata for {composer_name!r} ({qid})",
        file=sys.stderr,
    )
    if not musicids:
        print(
            f"  Tip: check https://www.wikidata.org/wiki/{qid} — "
            f"works may lack P856/P953 Boosey URLs in Wikidata.",
            file=sys.stderr,
        )
    return sorted(musicids)


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
    ap = argparse.ArgumentParser(description="Scrape Boosey & Hawkes instrumentation data")
    ap.add_argument("musicids", nargs="*", type=int, help="Boosey musicid(s) to fetch directly")
    ap.add_argument("--composer", action="append", default=[],
                    help="Fetch all works for a composer via Wikidata (repeatable)")
    ap.add_argument("--qid", help="Wikidata QID for the composer (e.g. Q7315) — skips name lookup; applies to the first --composer")
    ap.add_argument("--out-dir", default="data", help="Output directory (default: data/)")
    ap.add_argument("--force",   action="store_true", help="Overwrite existing files")
    ap.add_argument("--dry-run", action="store_true", help="Parse and print without writing files")
    args = ap.parse_args()

    ids: list[int] = list(args.musicids)

    for i, composer in enumerate(args.composer):
        qid = args.qid if i == 0 else None
        ids.extend(list_composer_works(composer, qid=qid))

    if not ids:
        ap.print_help()
        sys.exit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)

    ok = skip = fail = 0
    for mid in ids:
        print(f"Fetching musicid={mid}", file=sys.stderr)
        entry = build_entry(mid)
        if entry is None:
            fail += 1
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
