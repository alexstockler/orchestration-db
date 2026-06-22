"""Structured instrumentation model — the source of truth.

The Daniels-style formula string is a *rendering* of this model, never the
storage format. See render.py / parse.py.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from . import vocab


@dataclass
class Player:
    """One seat in a woodwind or brass family.

    instrument: None means "the family default" (e.g. plain flute). A non-None
        value means this player's PRIMARY instrument is an auxiliary
        (e.g. a dedicated contrabassoon chair).
    doublings: auxiliaries this same player also covers.
    """
    instrument: Optional[str] = None
    doublings: list[str] = field(default_factory=list)

    @staticmethod
    def from_obj(obj) -> "Player":
        if obj is None:
            return Player()
        if isinstance(obj, dict):
            return Player(obj.get("instrument"), list(obj.get("doublings", [])))
        raise TypeError(f"bad player: {obj!r}")

    def to_obj(self):
        out = {}
        if self.instrument:
            out["instrument"] = self.instrument
        if self.doublings:
            out["doublings"] = list(self.doublings)
        return out or None


def _players(value, default_key: str) -> list[Player]:
    """Normalise a family value. Accepts an int count or a list of player dicts."""
    if value is None:
        return []
    if isinstance(value, int):
        return [Player() for _ in range(value)]
    return [Player.from_obj(p) for p in value]


@dataclass
class Percussion:
    timpani: int = 0          # number of timpanists
    players: int = 0          # number of other percussionists
    instruments: list[str] = field(default_factory=list)

    @staticmethod
    def from_obj(obj) -> "Percussion":
        obj = obj or {}
        return Percussion(obj.get("timpani", 0), obj.get("players", 0),
                          list(obj.get("instruments", [])))

    def to_obj(self):
        out = {}
        if self.timpani:
            out["timpani"] = self.timpani
        if self.players:
            out["players"] = self.players
        if self.instruments:
            out["instruments"] = list(self.instruments)
        return out


@dataclass
class KeyboardPlayer:
    instrument: str
    doublings: list[str] = field(default_factory=list)

    @staticmethod
    def from_obj(obj) -> "KeyboardPlayer":
        if isinstance(obj, str):
            return KeyboardPlayer(obj)
        return KeyboardPlayer(obj["instrument"], list(obj.get("doublings", [])))

    def to_obj(self):
        out = {"instrument": self.instrument}
        if self.doublings:
            out["doublings"] = list(self.doublings)
        return out


@dataclass
class Strings:
    standard: bool = True             # True -> renders as "str"
    description: str = ""             # freeform, e.g. "3vn 3va 3vc" for a string work
    continuo: bool = False

    @staticmethod
    def from_obj(obj) -> "Strings":
        if obj is None:
            return Strings()
        if isinstance(obj, str):           # shorthand: "str" or a description
            return Strings(standard=(obj.strip() == "str"),
                           description="" if obj.strip() == "str" else obj.strip())
        return Strings(obj.get("standard", True), obj.get("description", ""),
                       obj.get("continuo", False))

    def to_obj(self):
        if self.standard and not self.continuo and not self.description:
            return "str"
        out = {"standard": self.standard}
        if self.description:
            out["description"] = self.description
        if self.continuo:
            out["continuo"] = True
        return out


@dataclass
class Instrumentation:
    flute: list[Player] = field(default_factory=list)
    oboe: list[Player] = field(default_factory=list)
    clarinet: list[Player] = field(default_factory=list)
    bassoon: list[Player] = field(default_factory=list)
    horn: list[Player] = field(default_factory=list)
    trumpet: list[Player] = field(default_factory=list)
    trombone: list[Player] = field(default_factory=list)
    tuba: list[Player] = field(default_factory=list)
    percussion: Percussion = field(default_factory=Percussion)
    keyboards: list[KeyboardPlayer] = field(default_factory=list)
    harp: int = 0
    extras: list[KeyboardPlayer] = field(default_factory=list)  # gtr, mand, ...
    strings: Optional[Strings] = None
    # non-formula structured fields
    soloists: list[str] = field(default_factory=list)
    chorus: list[str] = field(default_factory=list)
    chorus_raw: str = ""
    saxophones: list = field(default_factory=list)   # [{instrument, count}]
    additional_raw: str = ""                          # uncategorised extras
    offstage: str = ""

    @staticmethod
    def from_obj(obj) -> "Instrumentation":
        obj = obj or {}
        inst = Instrumentation()
        for fam in vocab.WOODWIND_FAMILIES + vocab.BRASS_FAMILIES:
            setattr(inst, fam, _players(obj.get(fam), vocab.FAMILY_DEFAULT[fam]))
        inst.percussion = Percussion.from_obj(obj.get("percussion"))
        inst.keyboards = [KeyboardPlayer.from_obj(k) for k in obj.get("keyboards", [])]
        inst.harp = obj.get("harp", 0)
        inst.extras = [KeyboardPlayer.from_obj(k) for k in obj.get("extras", [])]
        inst.strings = Strings.from_obj(obj["strings"]) if "strings" in obj else None
        inst.soloists = list(obj.get("soloists", []))
        inst.chorus = list(obj.get("chorus", []))
        inst.chorus_raw = obj.get("chorus_raw", "")
        inst.saxophones = list(obj.get("saxophones", []))
        inst.additional_raw = obj.get("additional_raw", "")
        inst.offstage = obj.get("offstage", "")
        return inst

    def to_obj(self):
        out = {}
        for fam in vocab.WOODWIND_FAMILIES + vocab.BRASS_FAMILIES:
            players = getattr(self, fam)
            if not players:
                continue
            objs = [p.to_obj() for p in players]
            # collapse to an int when every player is the plain family default
            if all(o is None for o in objs):
                out[fam] = len(players)
            else:
                out[fam] = [o if o is not None else {} for o in objs]
        if self.percussion.to_obj():
            out["percussion"] = self.percussion.to_obj()
        if self.keyboards:
            out["keyboards"] = [k.to_obj() for k in self.keyboards]
        if self.harp:
            out["harp"] = self.harp
        if self.extras:
            out["extras"] = [k.to_obj() for k in self.extras]
        if self.strings is not None:
            out["strings"] = self.strings.to_obj()
        if self.soloists:
            out["soloists"] = list(self.soloists)
        if self.chorus:
            out["chorus"] = list(self.chorus)
        if self.chorus_raw:
            out["chorus_raw"] = self.chorus_raw
        if self.saxophones:
            out["saxophones"] = list(self.saxophones)
        if self.additional_raw:
            out["additional_raw"] = self.additional_raw
        if self.offstage:
            out["offstage"] = self.offstage
        return out
