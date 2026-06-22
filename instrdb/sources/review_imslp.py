#!/usr/bin/env python3
"""Review tool: show all unrecognised fragments from a batch IMSLP scrape.

Usage:
    # Re-parse raw scoring strings saved in provenance notes and show unknowns:
    python -m instrdb.sources.review_imslp

    # Filter to show only entries that still have additional_raw:
    python -m instrdb.sources.review_imslp --unresolved-only

    # Re-parse and show what would change if we updated the parser:
    python -m instrdb.sources.review_imslp --reparse

Output is a markdown-formatted table so you can paste it into a GitHub issue
or chat to identify which free-text fragments need parser improvements.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from .parse_imslp_scoring import parse_imslp_scoring


def _collect_entries(data_dir: Path) -> list[dict]:
    entries = []
    for path in sorted(data_dir.glob("*.yaml")):
        with path.open() as f:
            entry = yaml.safe_load(f)
        if entry.get("provenance", {}).get("source") == "imslp":
            entries.append({"path": path, "entry": entry})
    return entries


def _reparse(entry: dict) -> dict:
    notes = entry.get("provenance", {}).get("notes", "")
    m = re.match(r"^Instrumentation:\s*(.*)", notes, re.S)
    if not m:
        return {}
    return parse_imslp_scoring(m.group(1).strip())


def main():
    ap = argparse.ArgumentParser(description="Review IMSLP unrecognised fragments")
    ap.add_argument("--data-dir", default="data", help="Data directory (default: data/)")
    ap.add_argument("--unresolved-only", action="store_true",
                    help="Only show entries with additional_raw set")
    ap.add_argument("--reparse", action="store_true",
                    help="Re-parse original scoring strings through current parser")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    entries = _collect_entries(data_dir)

    if not entries:
        print("No IMSLP entries found in", data_dir)
        sys.exit(0)

    print(f"## IMSLP Instrumentation Review — {len(entries)} entries\n")
    print(f"| File | Work | Raw Instrumentation | Unrecognised fragments |")
    print(f"|------|------|---------------------|------------------------|")

    shown = 0
    for item in entries:
        entry = item["entry"]
        path = item["path"]

        if args.reparse:
            result = _reparse(entry)
            unrecognised = result.get("unrecognised", [])
            additional = result.get("instrumentation", {}).get("additional_raw", "")
        else:
            additional = entry.get("instrumentation", {}).get("additional_raw", "")
            unrecognised = [additional] if additional else []

        if args.unresolved_only and not unrecognised:
            continue

        raw = entry.get("provenance", {}).get("notes", "")
        raw = re.sub(r"^Instrumentation:\s*", "", raw).strip()[:100]
        work = f"{entry.get('work', {}).get('composer', '')} – {entry.get('work', {}).get('title', '')}"
        frags = "; ".join(unrecognised) if unrecognised else "—"

        print(f"| {path.name} | {work} | {raw}… | {frags} |")
        shown += 1

    print(f"\n_{shown} entries shown._")

    if args.reparse and shown > 0:
        print("\n### Unique unrecognised fragments across all entries\n")
        all_frags: dict[str, list[str]] = {}
        for item in entries:
            result = _reparse(item["entry"])
            for frag in result.get("unrecognised", []):
                all_frags.setdefault(frag, []).append(item["path"].name)
        for frag, sources in sorted(all_frags.items(), key=lambda x: -len(x[1])):
            print(f"- `{frag}` ({len(sources)}x): {', '.join(sources[:5])}")


if __name__ == "__main__":
    main()
