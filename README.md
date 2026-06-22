# Orchestration DB

An open, queryable database of orchestral instrumentation for the classical
repertoire — an open-source counterpart to *Daniels' Orchestral Music*. The
shorthand looks like:

```
2222 4231 tmp+3 pf/cel hp str
```

…but that string is **generated**. The source of truth is structured data, so
you can actually query the collection ("everything with 3 trombones and no
tuba", "playable with 8 winds", "needs contrabassoon"), render any notation
convention, and verify entries automatically.

## What's here

```
instrdb/            the notation engine (Python, no framework)
  vocab.py          controlled instrument vocabulary + abbreviations
  model.py          structured data model (source of truth)
  render.py         structured  ->  Daniels-style formula
  parse.py          Daniels-style formula  ->  structured
  validate.py       schema + formula-consistency checker (CI entry point)
schema/work.schema.json   JSON Schema for a work entry
spec/NOTATION.md          the notation specification / grammar
data/*.yaml               example work entries (also used as fixtures)
tests/test_engine.py      render + round-trip conformance tests
```

## Try it

```bash
pip install pyyaml jsonschema
python tests/test_engine.py        # engine conformance
python -m instrdb.validate         # validate every data file
```

## Web UI (ingest console)

A local browser tool wrapping this same engine — paste a publisher scoring, see
the rendered formula, edit the entry, and save it (validated) into `data/`.

```bash
pip install -r requirements.txt
python webui/app.py        # then open http://127.0.0.1:5000
```

Tabs: **Ingest** (parse a Boosey scoring block, or fetch live by musicid),
**Formula tools** (formula ↔ structured data), **Library** (every entry in
`data/`, re-validated live). Fetch-by-musicid needs internet; the rest works
offline. Saving runs the full schema + formula check and rejects broken entries.


```python
from instrdb import Instrumentation, render, parse
render(parse("2222 4231 tmp+3 pf/cel hp str"))
# -> '2222 4231 tmp+3 pf/cel hp str'
```

## Data model in one breath

Three layers: a **work** (composer, title, catalog no., external IDs), a
**version/edition** (the same work can be scored differently across editions —
this is where instrumentation attaches), and the **instrumentation** itself,
where each wind/brass family is a list of players, each with a primary
instrument and optional doublings. Every entry carries **provenance** and a
**confidence** tier. See `schema/work.schema.json` and `spec/NOTATION.md`.

## Where the data comes from (and the one rule)

In order of legal cleanliness and reliability:

1. **Publisher catalog pages** (Boosey & Hawkes, Schott, Universal, Breitkopf,
   Bärenreiter…) — factual instrumentation; check each site's terms, prefer
   polite cached crawling, or just ask them.
2. **Public-domain scores themselves** (front-matter "Besetzung") via IMSLP —
   the most defensible source for pre-~1929 repertoire.
3. **IMSLP metadata** — MediaWiki API + the worklist API; the instrumentation
   field is free-text and multilingual, so treat it as a seed/cross-check.
4. **Seed lists** — OpenOpus, MusicBrainz, Wikidata (SPARQL) for the work
   universe and the external IDs that anchor identity.

**The rule:** facts (a work's instrumentation) are not copyrightable, but a
*compilation* is. Derive every datum from sources 1–4; never transcribe Daniels
or copy its editorial extras. If a datum's only source is Daniels, it doesn't go
in.

## Confidence tiers

`score_verified` > `multi_source` > `single_source` > `unverified`. Surface this
in any UI; it's what makes the dataset trustworthy rather than just large.

## Suggested licensing

Code: MIT or Apache-2.0. Data: CC0 (cleanest for a facts database) or ODbL if
you want share-alike on downstream databases.

## Roadmap

* **Phase 0 (now):** schema + engine + a handful of hand-verified edge cases.
* **Phase 1:** the ~2–3k most-programmed works, human-verified (≈80% of the
  practical value).
* **Phase 2:** scale via IMSLP/publisher ingestion + community PRs,
  public-domain first.
* **Phase 3:** public API, a search UI, federation back to Wikidata.

## Contributing model

One YAML file per work, contributed via pull request. CI runs
`instrdb.validate` on every PR: schema check, controlled-vocabulary check,
formula must equal `render(instrumentation)`, formula must round-trip. That keeps
a large, crowd-sourced dataset internally consistent.
