# Instrumentation Notation Specification (v0.1 draft)

A formal description of the shorthand "formula" used by this project. It adopts
the conventions of *Daniels' Orchestral Music* — the de-facto standard among
orchestral librarians — and pins down the cases Daniels leaves implicit. The
formula is always **generated from structured data**, never the other way
around; this document exists so the generator and parser agree, and so humans
can read and write it unambiguously.

## 1. Overview

A formula is a single line composed of space-separated sections, in this order:

```
<woodwinds><brass>  <percussion>  <keyboards>  <harp>  <extras>  <strings>
```

The woodwind and brass blocks together form the "wind/brass formula". Sections
that are empty are omitted entirely (including both wind/brass blocks for a
string-only work).

## 2. Woodwind and brass blocks

* Woodwind families, in fixed order: **flute, oboe, clarinet, bassoon**.
* Brass families, in fixed order: **horn, trumpet, trombone, tuba**.
* A single space separates the woodwind block from the brass block. No other
  delimiter is used between them.

Each family renders as either a **count** or an **amplified family**:

* **Count** — a single digit giving the number of players (`2`). A family with
  zero players still renders as `0` *within* a block when other families in that
  block are present (so a horns-only brass block is `4000`).
* **Amplified family** — `N[player.player. ...]` when any player in the family
  plays an auxiliary instrument. `N` is the player count; inside the brackets a
  **dot (`.`) separates players** and a **slash (`/`) marks a doubling**.

### Block compaction rule

* If **every** family in a block is a plain count (no amplification) and each
  count is a single digit, the digits are **concatenated**: `2222`, `4231`.
* If **any** family in the block is amplified, the **whole block is
  space-separated** and plain families render as bare digits:
  `3[1.2.3/pic] 2 2 2`.

### Player tokens (inside brackets)

A player is identified by its position number unless its *primary* instrument is
an auxiliary:

| Situation                                   | Token      | Meaning                                  |
|---------------------------------------------|------------|------------------------------------------|
| Plays the family default                    | `2`        | player 2 plays the normal instrument     |
| Default + doubles an auxiliary              | `3/pic`    | player 3 plays flute, doubles piccolo    |
| Default + two doublings                     | `2/Ebcl/bcl` | player 2 doubles both                  |
| Primary instrument *is* the auxiliary       | `cbn`      | a dedicated contrabassoon chair          |

Example: `3[1.2.cbn]` = three "bassoon" players where the third plays only
contrabassoon. `2[1.2/pic]` = two flutes, the second doubling piccolo.

## 3. Percussion

* `tmp` — timpani present (one timpanist).
* `tmp+N` — timpani plus `N` additional percussionists.
* `Nperc` — `N` percussionists, no timpani.
* `perc` — percussion present, count unspecified (treated as ≥1).

The specific instrument list (snare, glockenspiel, …) is carried in the
structured data, not in the formula.

## 4. Keyboards, harp, extras, strings

* **Keyboards** render by abbreviation; one player's doublings join with `/`:
  `pf/cel` is one player on piano and celesta; `pf cel` is two separate players.
  Abbreviations: `pf` piano, `cel` celesta, `hpd` harpsichord, `org` organ,
  `harm` harmonium.
* **Harp** — `hp` for one, `Nhp` for several (`2hp`).
* **Extras** — plucked/other single players: `gtr`, `mand`, `banjo`, `acc`.
* **Strings**:
  * `str` — standard string section.
  * A freeform descriptor for non-standard scoring (e.g. `3vn 3va 3vc`).
  * `cont` — continuo present (appended).

## 5. Structured fields not shown in the formula

Soloists, chorus, and offstage forces are kept as structured fields and are not
part of the rendered formula. Programmers and librarians query them directly.

## 6. Worked examples

| Formula | Reading |
|---|---|
| `1222 2000 str` | 1 fl, 2 ob, 2 cl, 2 bn; 2 hn; strings |
| `2222 4231 tmp+3 pf/cel hp str` | full double winds, full brass, timpani + 3 perc, one keyboard player on piano/celesta, harp, strings |
| `2[1.2/pic] 2 2 3[1.2.cbn] 2230 tmp str` | 2 fl (2nd doubles picc), 2 ob, 2 cl, 3 bsn (3rd is contra); 2 hn, 2 tpt, 3 tbn; timpani; strings |
| `3 3[1.2.Eh] 2 2 4000 1perc 2hp str` | 3 fl, 2 ob + cor anglais, 2 cl, 2 bn; 4 hn; 1 perc; 2 harps; strings |
| `3vn 3va 3vc cont` | string work: 3 each vn/va/vc plus continuo |

## 7. Deprecated forms (not parsed)

Older Daniels editions used a cruder scheme with `*`, `+`, and `=` to flag the
*presence* of auxiliary woodwinds without saying how many or which player covered
them. That scheme is ambiguous and intentionally unsupported here; always use the
bracketed form above.

## 8. Known limitations of the current parser

* Counts of 10+ in a wind/brass family must use the bracketed form; a bare
  multi-digit token (e.g. `12`) is interpreted as the compact digits `1` and `2`.
* No alternate inter-section separators (some writers use a long dash) are
  accepted; sections are space-separated only.
* Voices/soloists/offstage are not encoded in the formula by design.
