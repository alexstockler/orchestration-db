#!/usr/bin/env python3
"""Fetch Boosey & Hawkes catalogue pages and emit schema entries.

Usage:
    python -m instrdb.sources.scrape_boosey 6803 6144 ...

For each musicid it requests
    https://www.boosey.com/pages/cr/catalogue/cat_detail?musicid=<id>
extracts the Title / dates / duration / Scoring block, runs the Boosey parser,
and writes data/<slug>.yaml.

NOTE ON ENUMERATION: the per-composer work *listing*
(/cr/catalogue/ps/powersearch_results?composerid=...&DL_ClassificationGroupIDs=...)
is rendered client-side with JavaScript, so a plain HTTP GET returns an empty
shell. To enumerate every orchestral work, drive that page with a headless
browser (Playwright) and collect the musicid links, then feed them here. The
orchestra-relevant classification group IDs are:
    14068 Full Orchestra      14069 Chamber Orchestra
    14070 Solo instrument(s) and Orchestra
    14071 Voice(s) and Orchestra   14074 Chorus and Orchestra
Be polite: cache responses, rate-limit, and respect robots.txt. Instrumentation
is factual and not copyrightable, but the catalogue compilation is Boosey's.
"""
import re
import sys
import urllib.request

import yaml

from .boosey import parse_scoring

DETAIL = "https://www.boosey.com/pages/cr/catalogue/cat_detail?musicid={}"
UA = "orchestration-db/0.1 (open instrumentation database; contact: you@example.org)"


def slugify(composer: str, title: str) -> str:
    base = f"{composer}-{title}".lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    return base.strip("-")


def fetch(musicid: int) -> str:
    req = urllib.request.Request(DETAIL.format(musicid), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def extract_fields(html: str) -> dict:
    """Pull title, composer, dates, duration and the Scoring block from HTML."""
    title = ""
    mh1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if mh1:
        title = re.sub(r"<[^>]+>", "", mh1.group(1)).strip()
    composer = ""
    mc = re.search(r'/composer/[^"\']*"[^>]*>\s*([^<]+?)\s*</a>', html)
    if mc:
        composer = mc.group(1).strip()
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    myear = re.search(r"\((\d{4}(?:[-/]\d{2,4})?)\)", text)
    dur = re.search(r"Duration:\s*([0-9]+)['\u2019]", text)
    scoring = re.search(r"Scoring\s+(.*?)\s+(?:Abbreviations|Publisher|Opera|Programme|Repertoire)", text)
    return {
        "title": title,
        "composer": composer,
        "year": myear.group(1) if myear else None,
        "duration_minutes": int(dur.group(1)) if dur else None,
        "scoring": scoring.group(1).strip() if scoring else "",
    }


def build_entry(musicid: int, composer: str, title: str, year=None) -> dict:
    html = fetch(musicid)
    fields = extract_fields(html)
    parsed = parse_scoring(fields["scoring"])
    entry = {
        "id": slugify(composer, title),
        "work": {"composer": composer, "title": title,
                 "ids": {"boosey": str(musicid)}},
        "version": {"publisher": "Boosey & Hawkes"},
        "formula": parsed["formula"],
        "instrumentation": parsed["instrumentation"],
        "provenance": {
            "source": "publisher:boosey",
            "source_url": DETAIL.format(musicid),
            "confidence": "single_source",
            "notes": "Scoring: " + parsed["scoring_raw"],
        },
    }
    if year:
        entry["work"]["year"] = year
    if fields["duration_minutes"]:
        entry["duration_minutes"] = fields["duration_minutes"]
    return entry


if __name__ == "__main__":
    for mid in sys.argv[1:]:
        e = build_entry(int(mid), "Andriessen, Louis", f"musicid-{mid}")
        path = f"data/{e['id']}.yaml"
        with open(path, "w") as fh:
            yaml.safe_dump(e, fh, allow_unicode=True, sort_keys=False)
        print("wrote", path)
