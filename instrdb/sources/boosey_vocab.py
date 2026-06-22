"""Map Boosey & Hawkes scoring abbreviations to our canonical instrument keys.

Source: B&H "Standard Scoring and Language Abbreviations" (official PDF). Boosey
uses different tokens from our Daniels-style abbreviations (corA vs Eh, dbn vs
cbn, pft vs pf, trbn vs tbn, ...), so this is a dedicated translation table.
"""

# Boosey token -> our canonical key
BOOSEY_TO_KEY = {
    # woodwind
    "picc": "piccolo", "fl": "flute", "afl": "alto_flute", "bfl": "bass_flute",
    "rec": "recorder",
    "ob": "oboe", "corA": "english_horn",
    "cl": "clarinet", "Ebcl": "eflat_clarinet", "bcl": "bass_clarinet",
    "dbcl": "contrabass_clarinet", "bhn": "basset_horn",
    "ssax": "soprano_sax", "asax": "alto_sax", "tsax": "tenor_sax",
    "barsax": "baritone_sax",
    "bn": "bassoon", "dbn": "contrabassoon",
    # brass
    "hn": "horn", "thn": "tenor_horn", "crt": "cornet", "flgn": "flugelhorn",
    "tpt": "trumpet", "picc.tpt": "piccolo_trumpet", "atpt": "alto_trumpet",
    "btpt": "bass_trumpet",
    "trbn": "trombone", "atrbn": "alto_trombone", "ttrbn": "tenor_trombone",
    "btrbn": "bass_trombone",
    "euph": "euphonium", "ttuba": "tuba", "tuba": "tuba",
    # percussion / keyboards / other
    "timp": "timpani", "perc": "percussion",
    "cel": "celesta", "pft": "piano", "hpd": "harpsichord", "org": "organ",
    "harm": "harmonium", "synth": "synthesizer", "gtr": "guitar",
    "elec.gtr": "electric_guitar", "mand": "mandolin", "cimbalom": "cimbalom",
    # strings
    "vln": "violin", "vla": "viola", "vlc": "cello", "db": "double_bass",
}

# Which of our families a canonical key belongs to (for nesting auxiliaries).
KEY_FAMILY = {
    "piccolo": "flute", "alto_flute": "flute", "bass_flute": "flute",
    "english_horn": "oboe",
    "eflat_clarinet": "clarinet", "bass_clarinet": "clarinet",
    "contrabass_clarinet": "clarinet", "basset_horn": "clarinet",
    "contrabassoon": "bassoon",
    "bass_trumpet": "trumpet", "piccolo_trumpet": "trumpet",
    "alto_trumpet": "trumpet", "cornet": "trumpet", "flugelhorn": "trumpet",
    "alto_trombone": "trombone", "bass_trombone": "trombone",
    "tenor_trombone": "trombone",
    "tenor_horn": "horn",
}

SAX_KEYS = {"soprano_sax", "alto_sax", "tenor_sax", "baritone_sax"}
