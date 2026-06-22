# Source: Boosey & Hawkes

Boosey publishes a **Scoring** block on every catalogue work page
(`cat_detail?musicid=…`), in their house shorthand. Their official
*Standard Scoring and Language Abbreviations* PDF is the authoritative key, and
`instrdb/sources/boosey_vocab.py` encodes it. The format is richer than Daniels'
compact form — it records *which* player doubles, via roman numerals.

## Grammar

```
[VOICES ;] [chorus(...)]  WW - BRASS - PERC - <others...> - strings(...)
```

* Groups separated by hyphens; first is woodwind, second brass (dot-separated).
* Bare numbers fill the canonical families in order (ww: fl·ob·cl·bn; brass:
  hn·tpt·trbn·tuba). Named entries (`2bcl`, `2asax`, `corA`) are explicit
  auxiliaries inserted in score order.
* `(III=picc)` = player III doubles piccolo; `(I,II,III=picc,III=afl)` assigns
  piccolo to I/II/III and alto flute to III.

`instrdb/sources/boosey.py` parses all of this into the structured model and
renders our formula. Celesta/synth/guitars/cimbalom and detailed percussion that
sit after the brass group are preserved verbatim in `additional_raw` rather than
force-fitted, and saxophones go in `saxophones` — nothing is lost.

## Two-step ingestion

**Extraction** (works today): given a `musicid`, fetch the server-rendered
`cat_detail` page and parse it. `instrdb/sources/scrape_boosey.py` does this and
writes a schema entry. Proven on real data — see
`data/andriessen-de-materie.yaml` and `data/andriessen-writing-to-vermeer.yaml`.

**Enumeration** (needs a headless browser): the per-composer listing
(`powersearch_results?composerid=…&DL_ClassificationGroupIDs=…`) is rendered
client-side, so a plain GET returns an empty shell. Drive it with Playwright,
collect the `musicid` links, then feed them to the scraper. "Anything involving
an orchestra" = these classification groups:

| ID | Group |
|----|-------|
| 14068 | Full Orchestra |
| 14069 | Chamber Orchestra |
| 14070 | Solo instrument(s) and Orchestra |
| 14071 | Voice(s) and Orchestra |
| 14074 | Chorus and Orchestra |

(Operas `14066` and Ballets `14067` also use an orchestra; include them if you
want stageworks.)

## Worked example for composer 3287 (Louis Andriessen)

`composerid=3287` redirects to Andriessen's canonical `composerid=2690`. Two of
his works are ingested as proof:

* **De Materie** (1985–88) → `3 4[1.2.3/Eh.4/Eh] 8[1.2.3.4.5.bcl.bcl.bcl/cbcl] 0 4441 tmp+6 pf pf hp 2.2.2.2.1` plus 2·2·1 saxes; large ensemble.
* **Writing to Vermeer** (1997–98) → `3[1/pic.2/pic.3/pic/afl] 2[1/Eh.2/Eh] 2[bcl.bcl/cbcl] 0 2 2[1.2/btpt] 0 0 tmp+2 pf pf 2hp 6.6.4.4.2`; opera with orchestra.

These are unusually wind/percussion/keyboard-heavy (Andriessen's hallmark); the
formula captures the orchestral core and `additional_raw`/`saxophones` hold the
rest.

## Etiquette & legality

Instrumentation is factual (not copyrightable), but the catalogue compilation is
Boosey's. Cache pages, rate-limit, set a descriptive User-Agent, respect
robots.txt, and record `source_url` on every entry (the scraper does). Boosey's
programme notes are explicitly reproducible with credit; we don't copy those.
