# Roadmap

Current state: **~2,100 works** across 18 composers (Beethoven, Brahms, Mahler,
Tchaikovsky, Bruckner, Sibelius, Dvořák, Schumann, Mendelssohn, Saint-Saëns,
Rimsky-Korsakov, Grieg, Debussy, Wagner + a handful of others), all from IMSLP
with a working scraper, parser, validator, and local web UI.

---

## Recommended order

### 1. Architecture & API  ← do this first

The YAML-flat-file approach is fine for a few thousand entries but will become
a bottleneck as the dataset grows and we add publisher data. Designing the
backend now avoids a painful migration later and shapes how clients will consume
the data.

**Tasks**

- [ ] Choose a database (SQLite for dev, Postgres for prod is a safe default;
      consider DuckDB if the primary workload is analytical queries)
- [ ] Define the relational schema — key tables: `works`, `composers`,
      `instruments`, `work_instruments` (join), `sources` (provenance per row)
- [ ] Write a migration script that loads existing YAML files into the DB
- [ ] Design a REST (or GraphQL) API — initial useful endpoints:
  - `GET /works?composer=Mahler&instrument=horn` — filter by instrument
  - `GET /works/:id` — full entry with provenance
  - `GET /composers` — index
  - `GET /instruments` — canonical instrument list
  - `GET /formula/:formula` — works matching a Daniels-style formula
- [ ] Pick a framework (FastAPI is a natural fit given the Python codebase)
- [ ] Replace the Flask web UI's file-system library with DB queries
- [ ] Write an OpenAPI spec so API consumers know what to expect

**Why first:** every subsequent workstream (more IMSLP data, publisher scraping)
produces rows that need to land somewhere. Building the target first means each
new data source slots straight in, rather than being piled onto a flat-file
directory and migrated later.

---

### 2. Expand IMSLP coverage  ← run in parallel with (1)

The scraper and parser are proven. This can continue incrementally while the
backend is being designed — new YAML files accumulate and get bulk-loaded once
the DB is ready.

**Composers still to add (suggested priority — large catalogs or high search
value first)**

| Composer | Approx. works |
|---|---|
| Haydn, Joseph | ~750 |
| Mozart, Wolfgang Amadeus | ~600 |
| Schubert, Franz | ~900 |
| Liszt, Franz | ~700 |
| Ravel, Maurice | ~80 |
| Stravinsky, Igor | ~100 |
| Prokofiev, Sergei | ~130 |
| Shostakovich, Dmitri | ~150 |
| Bartók, Béla | ~90 |
| Handel, George Frideric | ~600 |
| Vivaldi, Antonio | ~500 |
| Strauss, Richard | ~200 |
| Elgar, Edward | ~150 |
| Vaughan Williams, Ralph | ~100 |

**Parser improvements still outstanding**

- Chamber string instruments (`violin`, `cello`, `viola` as solo/desk entries)
  currently land in `additional_raw` — decide on a model representation for
  chamber/solo works
- Cyrillic work titles produce an empty ASCII slug (Rimsky-Korsakov edge case)
  — fall back to the IMSLP page name
- Compound tokens like `2 bassoons + 2 horns`, `N voices` ranges (`1-4 voices`)
- `N+M` instrument notation for non-bassoon families

---

### 3. Publisher scraping  ← start after architecture is stable

In-copyright contemporary works won't appear on IMSLP. Publisher catalogues
are the source, but each requires a different approach.

**Boosey & Hawkes** (`scrape_boosey.py` already exists)
- Detail pages are server-side rendered — the scraper already works
- The *listing* pages are JS-rendered; enumeration needs Playwright to collect
  `musicid` links before fetching detail pages
- Classification group IDs already documented in `scrape_boosey.py`

**Other publishers to consider**

| Publisher | Notes |
|---|---|
| Chester Music / Music Sales | Similar catalogue structure to Boosey |
| Universal Edition | Has a well-structured public catalogue |
| Schott Music | Good online catalogue |
| G. Ricordi | Italian repertoire, Puccini / Verdi etc. |
| Edition Peters | Broad 20th-century catalogue |

**Legal / ethical notes**
- Instrumentation facts are not copyrightable; catalogue text and descriptions
  are — scrape only the scoring field
- Always cache, rate-limit, and identify the crawler in User-Agent
- Check robots.txt per publisher before scraping
- Consider reaching out to publishers directly; some may provide data feeds

---

## Parking lot (not yet prioritised)

- **Deduplication** across sources — same work on both IMSLP and a publisher
  catalogue needs a canonical ID (Wikidata `Q` numbers are a good anchor)
- **Search / similarity** — "find works with the same instrumentation as
  Mahler 5" is a natural query once there's a real DB
- **Confidence scoring** — some IMSLP entries have thin instrumentation fields;
  cross-referencing a second source would raise confidence
- **Public API / hosted version** — once the data is substantial enough to be
  useful to external tools (DAWs, library systems, music education apps)
