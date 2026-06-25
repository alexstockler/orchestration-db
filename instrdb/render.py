"""Render an Instrumentation model to the Daniels-style shorthand formula.

Conventions (Daniels):
  * Woodwind block = flute oboe clarinet bassoon (in that order)
  * Brass block    = horn trumpet trombone tuba (in that order)
  * A single space separates the major blocks.
  * Within a block, if every family is a plain single-digit count, the digits
    are concatenated: "2222". If any family carries an amplification, the whole
    block is space-separated and amplified families expand to N[...].
  * Inside brackets, a dot (.) separates players; a slash (/) marks a doubling.
"""
from __future__ import annotations

from . import vocab
from .model import Instrumentation, Player


def _player_token(idx: int, p: Player, default_key: str) -> str:
    if p.instrument in (None, default_key):
        tok = str(idx)
    else:
        tok = vocab.abbrev(p.instrument)
    for d in p.doublings:
        tok += "/" + vocab.abbrev(d)
    return tok


def _family_atom(players: list[Player], default_key: str) -> tuple[str, bool]:
    """Return (token, amplified?) for one family. token is "" for absent."""
    n = len(players)
    amplified = any(p.doublings or (p.instrument not in (None, default_key))
                    for p in players)
    if not amplified and n < 10:
        return str(n), False
    body = ".".join(_player_token(i, p, default_key)
                    for i, p in enumerate(players, start=1))
    return f"{n}[{body}]", True


def _block(families: list[str], inst: Instrumentation) -> str:
    atoms, any_amp = [], False
    for fam in families:
        tok, amp = _family_atom(getattr(inst, fam), vocab.FAMILY_DEFAULT[fam])
        atoms.append(tok)
        any_amp = any_amp or amp
    if any_amp:
        return " ".join(atoms)
    return "".join(atoms)


def _percussion(inst: Instrumentation) -> str:
    perc = inst.percussion
    tmp, others = perc.timpani > 0, perc.players
    if tmp and others:
        return f"tmp+{others}"
    if tmp:
        return "tmp"
    if others:
        return f"{others}perc"
    return ""


def _keyboard_token(k) -> str:
    tok = vocab.abbrev(k.instrument)
    for d in k.doublings:
        tok += "/" + vocab.abbrev(d)
    return tok


def render(inst: Instrumentation) -> str:
    parts: list[str] = []

    ww_present = any(getattr(inst, f) for f in vocab.WOODWIND_FAMILIES)
    br_present = any(getattr(inst, f) for f in vocab.BRASS_FAMILIES)
    if ww_present or br_present:
        parts.append(_block(vocab.WOODWIND_FAMILIES, inst))
        parts.append(_block(vocab.BRASS_FAMILIES, inst))

    perc = _percussion(inst)
    if perc:
        parts.append(perc)

    if inst.keyboards:
        parts.append(" ".join(_keyboard_token(k) for k in inst.keyboards))

    if inst.harp:
        parts.append("hp" if inst.harp == 1 else f"{inst.harp}hp")

    if inst.extras:
        parts.append(" ".join(_keyboard_token(k) for k in inst.extras))

    if inst.strings is not None:
        s = inst.strings
        if s.standard:
            parts.append("str")
        elif s.description:
            # Non-standard section (e.g. "3vn 3va 3vc") — description IS the formula token
            parts.append(s.description)
        if s.continuo:
            parts.append("cont")

    return " ".join(p for p in parts if p)
