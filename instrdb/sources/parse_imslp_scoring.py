"""Parse an IMSLP instrumentation infobox string into our structured model.

IMSLP uses English prose rather than Daniels-style abbreviations. Format varies
considerably between entries, but common patterns are:

  "2 flutes (2nd doubling piccolo), 2 oboes, 2 clarinets, 2 bassoons,
   2 horns, 2 trumpets, timpani, strings"

  "3 flutes (3rd = piccolo), 2 oboes, English horn, 2 clarinets, bass clarinet,
   2 bassoons, contrabassoon, 4 horns, 3 trumpets, 3 trombones, tuba,
   timpani, percussion, harp, strings"

Strategy:
  1. Split on commas (and semicolons separating soloist list from orchestra).
  2. For each token, normalise to lowercase and look up in IMSLP_TO_KEY.
  3. Recognise count prefixes ("2 flutes", "3rd = piccolo").
  4. Recognise doubling annotations ("2nd doubling piccolo", "1st and 2nd = piccolo").
  5. Assign to the correct family / special field.
  6. Anything unrecognised goes to additional_raw for human review.
"""
from __future__ import annotations
import re

from .imslp_vocab import (
    IMSLP_TO_KEY, KEY_FAMILY, SAX_KEYS,
    VOICE_KEYS, CHORUS_KEYS, KEYBOARD_KEYS, EXTRA_KEYS,
)
from .. import vocab, render
from ..model import Instrumentation, Player, KeyboardPlayer, Strings, Percussion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ORDINALS = {
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    "6th": 6, "7th": 7, "8th": 8, "9th": 9,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
}

_WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _count_and_rest(token: str):
    """Extract a leading integer count from a token string.

    Returns (count, remainder_string). count is None if no number found.
    """
    m = re.match(r"^(\d+)\s+(.*)", token)
    if m:
        return int(m.group(1)), m.group(2).strip()
    w = token.split()[0] if token.split() else ""
    if w in _WORD_NUMS:
        return _WORD_NUMS[w], token[len(w):].strip()
    return None, token


def _lookup(name: str):
    """Look up a normalised instrument name. Returns canonical key or None."""
    name = _normalise(name)
    if name in IMSLP_TO_KEY:
        return IMSLP_TO_KEY[name]
    # Try stripping trailing 's' for plural forms not already in table
    if name.endswith("s") and name[:-1] in IMSLP_TO_KEY:
        return IMSLP_TO_KEY[name[:-1]]
    return None


def _parse_doubling_clause(clause: str):
    """Parse a parenthetical like '2nd doubling piccolo' or '3rd = piccolo'.

    Returns list of (player_index: int, instrument_key: str) pairs,
    or empty list if not parseable.
    """
    results = []
    clause = clause.strip()

    # Pattern: "Nth [and Mth] [doubling|=|also playing|doubles] <instrument>"
    # Capture the ordinal(s) and instrument name.
    m = re.match(
        r"^((?:(?:1st|2nd|3rd|\d+th|first|second|third|fourth|fifth|sixth|"
        r"seventh|eighth|ninth|tenth)(?:\s+and\s+)?)+)"
        r"(?:\s*(?:doubling|=|also|also playing|doubles|alternating with|"
        r"doubling on|playing|can double|doubling)\s*:?\s*)"
        r"(.+)$",
        clause, re.I,
    )
    if m:
        idx_part = m.group(1).strip()
        instr_part = m.group(2).strip()
        # Extract all ordinals
        indices = [_ORDINALS[t.lower()] for t in re.findall(
            r"1st|2nd|3rd|\d+th|first|second|third|fourth|fifth|"
            r"sixth|seventh|eighth|ninth|tenth", idx_part, re.I
        ) if t.lower() in _ORDINALS]
        # Instrument may list multiple separated by "and" or "/"
        instruments = [p.strip() for p in re.split(r"\s+and\s+|/", instr_part) if p.strip()]
        for instr in instruments:
            key = _lookup(instr)
            if key:
                for idx in indices:
                    results.append((idx, key))
            else:
                # record unrecognised doubling as raw text
                for idx in indices:
                    results.append((idx, f"?:{instr}"))
    return results


# ---------------------------------------------------------------------------
# Main token processor
# ---------------------------------------------------------------------------

class _ParseState:
    def __init__(self):
        self.inst = Instrumentation()
        self.family_counts: dict[str, int] = {f: 0 for f in
                                               vocab.WOODWIND_FAMILIES + vocab.BRASS_FAMILIES}
        # family -> {player_index -> [doubling_keys]}
        self.family_doublings: dict[str, dict[int, list[str]]] = {
            f: {} for f in vocab.WOODWIND_FAMILIES + vocab.BRASS_FAMILIES
        }
        self.unrecognised: list[str] = []

    def _add_family_players(self, family: str, count: int,
                             primary_key: str | None = None):
        start = self.family_counts[family] + 1
        for i in range(start, start + count):
            p = Player(instrument=primary_key,
                       doublings=self.family_doublings[family].get(i, []))
            getattr(self.inst, family).append(p)
        self.family_counts[family] += count

    def _apply_doubling(self, family: str, player_idx: int, key: str):
        """Record a doubling for a specific player index in a family."""
        self.family_doublings[family].setdefault(player_idx, []).append(key)
        # If that player has already been added, patch it in-place
        players = getattr(self.inst, family)
        if player_idx <= len(players):
            p = players[player_idx - 1]
            if key not in p.doublings:
                p.doublings.append(key)

    def process_token(self, raw_token: str):
        # Strip leading colons from IMSLP wiki-list formatting artefacts
        token = _normalise(re.sub(r"^:+", "", raw_token))
        if not token:
            return

        # --- Split off parenthetical annotation ---
        paren_match = re.search(r"\(([^)]*)\)", token)
        paren_content = paren_match.group(1).strip() if paren_match else ""
        token_base = re.sub(r"\([^)]*\)", "", token).strip()

        count, name = _count_and_rest(token_base)

        key = _lookup(name) if name else _lookup(token_base)
        if key is None and count is not None:
            key = _lookup(name or "")

        # --- Voices / chorus ---
        if key in VOICE_KEYS:
            self.inst.soloists.append(name or token_base)
            return
        if key in CHORUS_KEYS:
            self.inst.chorus_raw = token_base
            return

        # --- Strings ---
        if token_base in ("strings", "string orchestra") or key in (
            "violin", "viola", "cello", "double_bass"
        ):
            if token_base == "strings" or token_base == "string orchestra":
                self.inst.strings = Strings(standard=True)
            else:
                # individual string desks — leave in additional_raw for now
                self.unrecognised.append(raw_token.strip())
            return

        # --- Timpani ---
        if key == "timpani":
            self.inst.percussion.timpani = max(self.inst.percussion.timpani,
                                               count or 1)
            return

        # --- Generic percussion ---
        if key == "percussion":
            name_lower = _normalise(name or token_base)
            if name_lower == "percussion":
                self.inst.percussion.players = max(self.inst.percussion.players,
                                                   count or 1)
            else:
                # Named instrument like "snare drum", "xylophone" etc.
                instr_name = name or token_base
                if instr_name not in self.inst.percussion.instruments:
                    self.inst.percussion.instruments.append(instr_name)
            return

        # --- Keyboards ---
        if key in KEYBOARD_KEYS:
            n = count or 1
            for _ in range(n):
                self.inst.keyboards.append(KeyboardPlayer(key))
            return

        # --- Harp ---
        if key == "harp":
            self.inst.harp += count or 1
            return

        # --- Extras (guitar, mandolin, etc.) ---
        if key in EXTRA_KEYS:
            self.inst.extras.append(KeyboardPlayer(key))
            return

        # --- Saxophones ---
        if key in SAX_KEYS:
            self.inst.saxophones.append({"instrument": key, "count": count or 1})
            return

        # --- Wind / Brass families ---
        family = KEY_FAMILY.get(key) if key else None

        if key in vocab.FAMILY_DEFAULT.values():
            # Primary family instrument (e.g. "flute", "oboe")
            family = next(f for f, d in vocab.FAMILY_DEFAULT.items() if d == key)
            n = count or 1
            self._add_family_players(family, n)
            if paren_content:
                self._process_paren(family, paren_content)
            return

        if family and key not in vocab.FAMILY_DEFAULT.values():
            # Auxiliary instrument used as a named extra chair in a family
            n = count or 1
            self._add_family_players(family, n, primary_key=key)
            return

        # --- Unrecognised ---
        if paren_content:
            # Token might be unrecognised but paren is a doubling annotation
            # Preserve everything
            self.unrecognised.append(raw_token.strip())
        else:
            self.unrecognised.append(raw_token.strip())

    def _process_paren(self, family: str, paren_content: str):
        """Process a doubling parenthetical attached to a family token."""
        # May have multiple clauses separated by "," or ";"
        for clause in re.split(r"[,;](?![^(]*\))", paren_content):
            clause = clause.strip()
            if not clause:
                continue
            pairs = _parse_doubling_clause(clause)
            for player_idx, dbl_key in pairs:
                if dbl_key.startswith("?:"):
                    self.unrecognised.append(
                        f"unknown doubling in {family}: {dbl_key[2:]}"
                    )
                else:
                    self._apply_doubling(family, player_idx, dbl_key)

    def build(self):
        """Finalise and return the Instrumentation object."""
        if self.unrecognised:
            self.inst.additional_raw = " | ".join(self.unrecognised)
        return self.inst


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _split_tokens(text: str) -> list[str]:
    """Split instrumentation prose into per-instrument tokens.

    Splits on commas and semicolons that are NOT inside parentheses.
    """
    tokens = re.split(r"[,;](?![^(]*\))", text)
    return [t.strip() for t in tokens if t.strip()]


def _strip_shorthand_prefix(text: str) -> str:
    """Remove a leading Daniels-style shorthand summary if present.

    Some IMSLP InstrDetail fields open with a compact line like:
      "2, 2, 2, 2+1 - 4, 2, 3, 0, timp, strs :2 flutes, 2 oboes, ..."
    A colon (or double-colon) separates that from the prose we want.
    """
    m = re.match(r"^[0-9,+\-\s\(\)a-z]*:+\s*(.+)", text, re.I | re.S)
    if m:
        prose = m.group(1).strip()
        # Accept if prose looks like "N instrument" or just "instrument"
        if re.match(r"(\d+\s+)?[a-zA-Z]", prose):
            return prose
    return text


def _expand_plus_notation(text: str) -> str:
    """Expand 'N+M family' shorthand into explicit comma-separated tokens.

    e.g. '2+1 bassoons' -> '2 bassoons, contrabassoon'
         '4+1 horns'    -> '4 horns'  (extra horn chair; no canonical aux)
    """
    def _replace(m):
        n, extra, family = int(m.group(1)), int(m.group(2)), m.group(3).strip().lower()
        if "bassoon" in family:
            aux = ", contrabassoon" * extra
            return f"{n} bassoons{aux}"
        # For other families just sum the counts
        return f"{n + extra} {family}"
    return re.sub(r"(\d+)\+(\d+)\s+(bassoons?|horns?|flutes?|oboes?|clarinets?|trumpets?|trombones?)",
                  _replace, text, flags=re.I)


def parse_imslp_scoring(text: str) -> dict:
    """Parse an IMSLP instrumentation string.

    Returns {instrumentation: dict, formula: str, scoring_raw: str,
             unrecognised: list[str]}.
    """
    raw = " ".join(text.split())
    raw = _strip_shorthand_prefix(raw)
    raw = _expand_plus_notation(raw)
    # Strip stray leading colons left over from IMSLP wiki-list formatting
    raw = re.sub(r"^:+\s*", "", raw)
    state = _ParseState()

    # Check for a voice/soloist preamble before the orchestral listing.
    # IMSLP sometimes lists soloists in a separate "for X, Y and orchestra" phrase.
    solo_pre = re.match(
        r"^for\s+(.+?)\s+(?:and\s+)?(?:orchestra|chamber orchestra|string orchestra|ensemble)",
        raw, re.I
    )
    if solo_pre:
        for tok in _split_tokens(solo_pre.group(1)):
            state.inst.soloists.append(tok.strip())
        raw = raw[solo_pre.end():].lstrip(":,; ")

    for token in _split_tokens(raw):
        state.process_token(token)

    inst = state.build()
    formula = render(inst)

    return {
        "instrumentation": inst.to_obj(),
        "formula": formula,
        "scoring_raw": " ".join(text.split()),
        "unrecognised": state.unrecognised,
    }
