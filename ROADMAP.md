# Roadmap

## Current state (2026-06-30)

**~10,036 works** across 76 composers. Fully deployed at
`https://orchestration-db-production.up.railway.app`.

### What's done

- **IMSLP scraper** — MediaWiki API, cached, rate-limited, ~76 composers ingested
- **Instrumentation parser** — Daniels-style formula + structured YAML model;
  handles solo strings, off-stage instruments, optional/ad lib. instruments
- **SQLite schema** — `works`, `composers`, `work_instruments`,
  `work_external_ids`, `work_provenance`
- **Migration** — `python -m instrdb.migrate` loads all YAML into the DB;
  runs automatically on Railway deploy
- **FastAPI** — `/works`, `/composers`, `/instruments`, `/works/{slug}`,
  `/query` (ad-hoc read-only SQL); OpenAPI docs at `/docs`
- **Web UI** — HTML search/browse at `/`
- **Railway deployment** — auto-deploys on push to `main`

---

## Ingestion log

| Date | Composers added | Works |
|---|---|---|
| (initial) | Beethoven, Brahms, Mahler, Tchaikovsky, Bruckner, Sibelius, Dvořák, Schumann, Mendelssohn, Saint-Saëns, Rimsky-Korsakov, Grieg, Debussy, Wagner, Andriessen, Bach, Bartók, Berlioz, Elgar, Handel, Haydn, Hindemith, Janáček, Liszt, Mozart, Nielsen, Prokofiev, Rachmaninoff, Ravel, Schubert, Shostakovich, Strauss R., Stravinsky, Vaughan Williams, Verdi, Vivaldi | ~5,466 |
| 2026-06-30 | Holst, Puccini, Bizet, Fauré, Franck | +385 → 6,043 |
| 2026-06-30 | Respighi, Smetana, Kodály | +193 → 6,236 |
| 2026-06-30 | Mussorgsky, Borodin, Gounod, Glazunov, Scriabin, Weber, Massenet, Offenbach, Lalo, Delibes | +1,189 → 7,425 |
| 2026-06-30 | Parser improvements re-parse (solo strings, offstage, optional) | 7,814 re-parsed |
| 2026-06-30 | Rossini (97), Donizetti (209), Cherubini (77), Spohr (163), Humperdinck (34), Chabrier (60), Chausson (50), Dukas (15), d'Indy (76), Balakirev (64), Arensky (61), Telemann (427), Rameau (60), Purcell (425), Corelli (39), Boccherini (69), Zemlinsky (29), Loewe (165) | +2,120 → 9,934 |
| 2026-06-30 | Goldmark, Carl (42); Taneyev, Sergey (58) | +100 → **10,036** |

**IMSLP name quirks to remember:**
- Russian composers: `Aleksandr` not `Alexander` (Borodin, Glazunov, Scriabin)
- `Prokofiev, Sergey` · `Rachmaninoff, Sergei` · `Shostakovich, Dmitry` · `Taneyev, Sergey`
- German: `Goldmark, Carl` (not Karl)
- French: `Indy, Vincent d'` (not "d'Indy, Vincent")
- Accented names must be passed exactly: `Fauré, Gabriel` · `Dvořák, Antonín` etc.

---

## What's next

### 1. Publisher scraping — Boosey & Hawkes  ← active

`scrape_boosey.py` exists and the detail-page fetcher works (plain HTTP).
The only missing piece is **enumeration**: getting the list of musicids for a
composer without browser automation.

**Fix**: replace the Playwright listing-page scraper with a Wikidata SPARQL
query. Wikidata property **P5099** = Boosey & Hawkes catalogue number.

```sparql
SELECT ?work ?bh WHERE {
  ?work wdt:P86 wd:Q<composer_qid> .
  ?work wdt:P5099 ?bh .
}
```

Query the Wikidata SPARQL endpoint (`https://query.wikidata.org/sparql`),
collect musicids, then pass them to the existing `build_entry(musicid)` detail
fetcher. No browser needed.

**Composers to prioritise** (large in-copyright catalogues):
| Composer | Wikidata QID | Notes |
|---|---|---|
| Britten, Benjamin | Q7315 | Core Boosey catalogue |
| Shostakovich, Dmitri | Q80726 | Many works in copyright |
| Prokofiev, Sergei | Q80330 | Ditto |
| Copland, Aaron | Q128505 | Major works not on IMSLP |
| Bartók, Béla | Q83326 | Some works still in copyright |
| Stravinsky, Igor | Q7314 | Later works in copyright |

**After Boosey is working**, the same Wikidata-enumeration pattern applies to:

| Publisher | Wikidata property | Notes |
|---|---|---|
| Chester Music / Music Sales | P5101 | Similar detail-page structure |
| Universal Edition | P5895 | Well-structured catalogue |
| Schott Music | P5893 | Good online catalogue |
| G. Ricordi | P5094 | Italian repertoire |
| Edition Peters | P5892 | Broad 20th-century catalogue |

**Legal / ethical notes**
- Instrumentation facts are not copyrightable — scrape only the scoring field
- Always cache, rate-limit, and send a descriptive User-Agent
- Check `robots.txt` per publisher before scraping

---

### 2. More IMSLP composers  ← run any time

All public domain (died before 1954). Run with:
`python -m instrdb.sources.scrape_imslp --composer "Name, Firstname" --out-dir data`

| Composer | Died | Notes |
|---|---|---|
| Zemlinsky, Alexander | 1942 | IMSLP uses "Zemlinsky, Alexander von" |
| Wolf, Hugo | 1903 | Large song catalog |
| Spohr, Louis | 1859 | 9 symphonies, large catalog |
| Loewe, Carl | 1869 | |
| Martinů, Bohuslav | 1959 | Some works PD in Canada only |
| Chabrier, Emmanuel | 1894 | España etc. |
| Balakirev, Mily | 1910 | IMSLP: "Balakirev, Mily" |

---

### 3. Deduplication

When a work appears in both IMSLP and a publisher catalogue, they should share
a canonical record rather than creating duplicates.

- **Anchor**: Wikidata Q number — already stored in `work_external_ids` when
  IMSLP includes it (many do). Publisher scraping adds the catalogue ID to the
  same record.
- **Confidence**: a work confirmed by two sources gets `multi_source` confidence
  in `work_provenance`; three or more gets `score_verified`.
- **Schema**: `work_external_ids` already supports multiple source rows per work.
  The migration needs a merge step: if a new YAML's Wikidata ID matches an
  existing work, add a provenance row rather than inserting a duplicate.

---

### 4. migrate.py improvements needed

- `solo_strings` dict not yet written to the DB — add a `work_solo_strings` table
  or fold into `work_instruments` with a `is_solo=1` flag
- `offstage` is stored as raw Python list repr (`"['carillon']"`) — should
  serialise to JSON or a proper `work_offstage` table
- `optional` flag on `Player` not yet propagated to `work_instruments`

---

## Parking lot

- **Formula search** — `GET /formula/3222+4331` finds works with that exact
  instrumentation; currently only free-text `q=` on formula string
- **Similarity** — "find works with same instrumentation as Mahler 5"
- **Confidence scoring UI** — surface `multi_source` vs `single_source` in
  search results
- **Public data dump** — nightly CSV/JSON export for external tools
