"""Parse a Boosey & Hawkes 'Scoring' string into our structured model.

Boosey grammar (from observed catalogue data + the official abbreviation PDF):

  [VOICES ;] [chorus(...)] WW - BRASS - PERC - <others...> - strings(...)

  * Major instrument groups are separated by hyphens.
  * The first group is woodwind, the second brass; both are dot-separated lists.
  * Bare numbers fill the canonical families in order (ww: fl.ob.cl.bn ;
    brass: hn.tpt.trbn.tuba). Named entries (e.g. '2bcl', '2asax', 'corA') are
    explicit auxiliaries inserted in score order.
  * Doublings are shown as '(III=picc)' — player III doubles piccolo. A list
    like '(I,II,III=picc,III=afl)' assigns picc to I/II/III and afl to III.

This is a v0 parser: it reliably extracts winds, brass, timpani presence,
percussion player count, harp count, piano count, and the string-desk layout.
Celesta/synth/guitars and detailed percussion lists that appear after the brass
group are preserved verbatim in `additional_raw` rather than force-fitted.
"""
from __future__ import annotations
import re

from .boosey_vocab import BOOSEY_TO_KEY, KEY_FAMILY, SAX_KEYS
from .. import vocab, render
from ..model import Instrumentation, Player

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
          "VII": 7, "VIII": 8, "IX": 9, "X": 10}
# match a single dot-separated entry: count, optional abbrev, optional (...)
_ENTRY = re.compile(r"^(\d*)\s*([A-Za-z.]+)?\s*(?:\((.*)\))?$")


def _split_voices(scoring: str):
    """Return (soloists_list, chorus_raw, instrument_part)."""
    soloists, chorus_raw = [], ""
    s = scoring.strip()
    # A leading soloist clause is terminated by ';'
    if ";" in s:
        head, s = s.split(";", 1)
        if not re.search(r"\d\.\d|-|strings", head):   # head looks like voices
            soloists = [t.strip() for t in head.split(",") if t.strip()]
        else:
            s = head + ";" + s   # not voices; put it back
    m = re.search(r"chorus\s*\(?([^)]*)\)?", s, re.I)
    if m and m.start() < (s.find("-") if "-" in s else len(s)):
        chorus_raw = m.group(1).strip()
        s = (s[:m.start()] + s[m.end():])
    return soloists, chorus_raw, s.strip()


def _parse_doublings(spec: str):
    """'I,II,III=picc,III=afl' -> {player_index: [aux_key, ...]}."""
    out: dict[int, list[str]] = {}
    if not spec:
        return out
    pending: list[int] = []
    for tok in spec.split(","):
        tok = tok.strip()
        if "=" in tok:
            left, aux = tok.split("=", 1)
            idxs = pending + ([_ROMAN[left.strip()]] if left.strip() in _ROMAN else [])
            key = BOOSEY_TO_KEY.get(aux.strip(), aux.strip())
            for i in idxs:
                out.setdefault(i, []).append(key)
            pending = []
        elif tok in _ROMAN:
            pending.append(_ROMAN[tok])
    return out


def _parse_group(group: str, families: list[str]):
    """Parse one dot-separated wind/brass group.

    Returns (family_players: dict, saxes: list, extras: list).
    """
    fam_players = {f: [] for f in families}
    queue = list(families)
    saxes, extras = [], []
    # split on '.' but not inside parentheses
    entries = re.split(r"\.(?![^()]*\))", group.strip())
    for raw in entries:
        raw = raw.strip()
        if not raw:
            continue
        m = _ENTRY.match(raw)
        if not m:
            continue
        count = int(m.group(1)) if m.group(1) else 1
        abbrev = (m.group(2) or "").strip(".")
        doublings = _parse_doublings(m.group(3) or "")

        if not abbrev:                       # bare number -> next canonical family
            fam = queue.pop(0) if queue else None
            if fam is None:
                continue
            players = []
            for i in range(1, count + 1):
                players.append(Player(doublings=doublings.get(i, [])))
            fam_players[fam] = players
            continue

        key = BOOSEY_TO_KEY.get(abbrev)
        if key in SAX_KEYS:
            saxes.append({"instrument": key, "count": count})
        elif key in KEY_FAMILY and KEY_FAMILY[key] in fam_players:
            fam = KEY_FAMILY[key]
            for i in range(1, count + 1):
                fam_players[fam].append(
                    Player(instrument=key, doublings=doublings.get(i, [])))
        else:
            extras.append(raw)
    return fam_players, saxes, extras


def parse_scoring(scoring: str) -> dict:
    """Parse a Boosey scoring string. Returns a dict ready for an entry."""
    soloists, chorus_raw, instr = _split_voices(scoring)

    # locate the first two hyphen group boundaries (ww | brass | rest)
    dashes = [m.start() for m in re.finditer(r"-", instr)]
    ww_str = brass_str = rest = ""
    if len(dashes) >= 2:
        ww_str = instr[:dashes[0]]
        brass_str = instr[dashes[0] + 1:dashes[1]]
        rest = instr[dashes[1] + 1:]
    elif len(dashes) == 1:
        ww_str, brass_str = instr[:dashes[0]], instr[dashes[0] + 1:]
    else:
        ww_str = instr

    inst = Instrumentation()
    ww, saxes, ww_extra = _parse_group(ww_str, vocab.WOODWIND_FAMILIES)
    br, _, br_extra = _parse_group(brass_str, vocab.BRASS_FAMILIES)
    for f in vocab.WOODWIND_FAMILIES:
        setattr(inst, f, ww[f])
    for f in vocab.BRASS_FAMILIES:
        setattr(inst, f, br[f])
    inst.saxophones = saxes

    # ---- post-brass groups: perc | keyboards | harp | extras | strings ----
    from ..model import KeyboardPlayer, Strings
    # percussion / timpani (counts read globally; robust to hyphenated detail)
    mperc = re.search(r"perc\((\d+)\)", rest)
    if mperc:
        inst.percussion.players = int(mperc.group(1))
    elif re.search(r"\bperc\b", rest):
        inst.percussion.players = 1
    if re.search(r"\btimp\b", rest):
        inst.percussion.timpani = 1

    KBD = {"cel": "celesta", "org": "organ", "hpd": "harpsichord",
           "harm": "harmonium"}
    leftover = []
    for frag in rest.split("-"):
        g = frag.strip()
        if not g:
            continue
        mpf = re.fullmatch(r"(\d*)\s*pft", g)
        mhp = re.fullmatch(r"(\d*)\s*harps?", g)
        mstr = re.match(r"strings?\b\s*\(?\s*(?:min\.?)?\s*([0-9.]*)\)?", g, re.I)
        kbd_key = next((v for k, v in KBD.items() if g == k or g.startswith(k + "(")), None)
        if mpf:
            n = int(mpf.group(1)) if mpf.group(1) else 1
            inst.keyboards += [KeyboardPlayer("piano") for _ in range(n)]
        elif kbd_key:
            inst.keyboards.append(KeyboardPlayer(kbd_key))
        elif mhp:
            inst.harp = int(mhp.group(1)) if mhp.group(1) else 1
        elif mstr:
            desks = mstr.group(1)
            inst.strings = (Strings(standard=False, description=desks) if desks
                            else Strings(standard=True))
        elif g.startswith("perc"):
            pass                              # already counted
        else:
            leftover.append(g)
    inst.additional_raw = " ".join(leftover)
    if soloists:
        inst.soloists = soloists
    if chorus_raw:
        inst.chorus_raw = chorus_raw

    obj = inst.to_obj()
    return {
        "instrumentation": obj,
        "formula": render(inst),
        "scoring_raw": " ".join(scoring.split()),
    }
