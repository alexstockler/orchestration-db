"""Controlled vocabulary for instrumentation.

Every instrument has a canonical snake_case KEY (used in the data files) and a
Daniels-style ABBREVIATION (used when rendering the shorthand formula).

The four woodwind families and four brass families each have a DEFAULT
instrument. A player whose primary instrument is the family default renders as a
bare position number (1, 2, 3...). Any other primary, or any doubling, renders
with its abbreviation.
"""

# Ordered families that make up the two grouped blocks of the formula.
WOODWIND_FAMILIES = ["flute", "oboe", "clarinet", "bassoon"]
BRASS_FAMILIES = ["horn", "trumpet", "trombone", "tuba"]

# Default (primary) instrument key for each family.
FAMILY_DEFAULT = {
    "flute": "flute",
    "oboe": "oboe",
    "clarinet": "clarinet",
    "bassoon": "bassoon",
    "horn": "horn",
    "trumpet": "trumpet",
    "trombone": "trombone",
    "tuba": "tuba",
}

# key -> abbreviation. Defaults map to "" because they render as bare numbers.
ABBREV = {
    # woodwinds
    "flute": "", "piccolo": "pic", "alto_flute": "afl", "bass_flute": "bfl",
    "oboe": "", "english_horn": "Eh", "oboe_damore": "obda",
    "heckelphone": "heck", "bass_oboe": "boboe",
    "clarinet": "", "eflat_clarinet": "Ebcl", "a_clarinet": "Acl",
    "bass_clarinet": "bcl", "basset_horn": "bhn",
    "contrabass_clarinet": "cbcl", "alto_clarinet": "altcl",
    "bassoon": "", "contrabassoon": "cbn",
    # brass
    "horn": "", "wagner_tuba": "Wtu",
    "trumpet": "", "piccolo_trumpet": "pictpt", "cornet": "cnt",
    "flugelhorn": "flhn", "bass_trumpet": "btpt",
    "trombone": "", "alto_trombone": "atbn", "bass_trombone": "btbn",
    "contrabass_trombone": "cbtbn",
    "tuba": "", "euphonium": "euph", "cimbasso": "cimb",
    # keyboards / plucked / other
    "piano": "pf", "celesta": "cel", "harpsichord": "hpd",
    "organ": "org", "harmonium": "harm", "synthesizer": "synth",
    "harp": "hp", "guitar": "gtr", "electric_guitar": "elgtr",
    "bass_guitar": "bgtr", "mandolin": "mand", "banjo": "banjo",
    "accordion": "acc", "cimbalom": "cimbalom",
    "timpani": "tmp", "percussion": "perc",
    # additional auxiliaries seen in publisher catalogues
    "recorder": "rec", "tenor_horn": "thn", "alto_trumpet": "atpt",
    "soprano_sax": "ssx", "alto_sax": "asx", "tenor_sax": "tsx",
    "baritone_sax": "barsx", "bass_sax": "bsx",
    "violin": "vln", "viola": "vla", "cello": "vlc", "double_bass": "db",
    # historical / rare instruments that appear in 19th-century scores
    "serpent": "serpent", "ophicleide": "ophicleide", "posthorn": "posthorn",
    "contrabass_tuba": "cbtba",
}

# Reverse map for the parser. Built only from non-empty abbreviations.
KEY_BY_ABBREV = {v: k for k, v in ABBREV.items() if v}

# Abbreviations that the parser should treat as keyboard/other "extra" players
# (rendered after the percussion block, before harp/strings).
KEYBOARD_KEYS = {"piano", "celesta", "harpsichord", "organ", "harmonium",
                 "synthesizer"}
EXTRA_KEYS = {"guitar", "electric_guitar", "bass_guitar", "mandolin", "banjo",
              "accordion", "cimbalom", "serpent", "ophicleide", "posthorn",
              "contrabass_tuba"}


def abbrev(key: str) -> str:
    """Return the rendering token for a key (its abbreviation, or the key if unknown)."""
    return ABBREV.get(key, key)


def is_known(key: str) -> bool:
    return key in ABBREV
