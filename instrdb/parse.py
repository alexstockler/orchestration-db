"""Parse a Daniels-style formula string back into an Instrumentation model.

Supports the canonical modern forms (compact blocks like "2222", amplified
families like "3[1.2.3/pic]", tmp+N / Nperc, pf/cel doublings, hp / Nhp, str,
cont, and freeform string-only descriptions). It does NOT attempt to parse the
deprecated * / + / = crude scheme used in old Daniels editions.

Known limitations are documented in spec/NOTATION.md.
"""
from __future__ import annotations
import re

from . import vocab
from .model import (Instrumentation, Player, Percussion, KeyboardPlayer,
                    Strings)

_BARE_INT = re.compile(r"^\d+$")
_BRACKET = re.compile(r"^(\d+)\[(.*)\]$")
_NPERC = re.compile(r"^(\d+)perc$")
_NHP = re.compile(r"^(\d+)hp$")


def _abbrev_to_key(tok: str) -> str:
    if tok in vocab.KEY_BY_ABBREV:
        return vocab.KEY_BY_ABBREV[tok]
    raise ValueError(f"unknown abbreviation: {tok!r}")


def _parse_player(token: str, default_key: str) -> Player:
    parts = token.split("/")
    head = parts[0]
    doublings = [_abbrev_to_key(p) for p in parts[1:]]
    instrument = None if head.isdigit() else _abbrev_to_key(head)
    return Player(instrument, doublings)


def _parse_family(token: str, default_key: str):
    """Return a family value: int count, or list[Player] for amplified families."""
    m = _BRACKET.match(token)
    if m:
        body = m.group(2)
        return [_parse_player(p, default_key) for p in body.split(".")]
    raise ValueError(f"not a family token: {token!r}")


def _is_wind_token(tok: str) -> bool:
    return bool(_BARE_INT.match(tok) or _BRACKET.match(tok))


def parse(formula: str) -> Instrumentation:
    tokens = formula.split()
    inst = Instrumentation()
    families: list = []   # collected ww+brass values, in order
    i = 0

    # ---- woodwind + brass blocks ----
    if tokens and _is_wind_token(tokens[0]):
        while i < len(tokens) and len(families) < 8 and _is_wind_token(tokens[i]):
            tok = tokens[i]
            if _BARE_INT.match(tok):
                for ch in tok:               # each digit is one family count
                    families.append(int(ch))
            else:
                families.append(_parse_family(tok, ""))
            i += 1
        while len(families) < 8:             # pad omitted families with 0
            families.append(0)

        order = vocab.WOODWIND_FAMILIES + vocab.BRASS_FAMILIES
        for fam, val in zip(order, families):
            players = ([Player() for _ in range(val)] if isinstance(val, int)
                       else val)
            setattr(inst, fam, players)

    # ---- everything after the wind/brass blocks ----
    description_buf: list[str] = []
    for tok in tokens[i:]:
        if tok.startswith("tmp"):
            inst.percussion.timpani = 1
            if "+" in tok:
                inst.percussion.players = int(tok.split("+", 1)[1])
        elif _NPERC.match(tok):
            inst.percussion.players = int(_NPERC.match(tok).group(1))
        elif tok == "perc":
            inst.percussion.players = max(inst.percussion.players, 1)
        elif tok == "hp":
            inst.harp = 1
        elif _NHP.match(tok):
            inst.harp = int(_NHP.match(tok).group(1))
        elif tok == "str":
            if inst.strings is None:
                inst.strings = Strings(standard=True)
        elif tok == "cont":
            if inst.strings is None:
                inst.strings = Strings(standard=False)
            inst.strings.continuo = True
        elif _is_keyboard(tok):
            inst.keyboards.append(_parse_keyboard(tok))
        elif _is_extra(tok):
            inst.extras.append(_parse_keyboard(tok))
        else:
            description_buf.append(tok)   # part of a string-section description

    if description_buf:
        if inst.strings is None:
            inst.strings = Strings(standard=False)
        desc = " ".join(description_buf)
        inst.strings.description = (
            (inst.strings.description + " " + desc).strip()
            if inst.strings.description else desc)
    return inst


def _head_key(tok: str):
    head = tok.split("/")[0]
    return vocab.KEY_BY_ABBREV.get(head)


def _is_keyboard(tok: str) -> bool:
    return _head_key(tok) in vocab.KEYBOARD_KEYS


def _is_extra(tok: str) -> bool:
    return _head_key(tok) in vocab.EXTRA_KEYS


def _parse_keyboard(tok: str) -> KeyboardPlayer:
    parts = tok.split("/")
    return KeyboardPlayer(_abbrev_to_key(parts[0]),
                          [_abbrev_to_key(p) for p in parts[1:]])
