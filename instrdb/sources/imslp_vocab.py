"""Map IMSLP instrumentation prose tokens to canonical instrument keys.

IMSLP uses English prose ("piccolo", "English horn", "bass clarinet") rather
than abbreviations. This table covers the most common variants and alternate
spellings found in IMSLP infoboxes.
"""

# English token (lowercase, stripped) -> canonical key
IMSLP_TO_KEY = {
    # flute family
    "flute": "flute",
    "flutes": "flute",
    "piccolo": "piccolo",
    "alto flute": "alto_flute",
    "bass flute": "bass_flute",
    # oboe family
    "oboe": "oboe",
    "oboes": "oboe",
    "english horn": "english_horn",
    "cor anglais": "english_horn",
    "oboe d'amore": "oboe_damore",
    "heckelphone": "heckelphone",
    # clarinet family
    "clarinet": "clarinet",
    "clarinets": "clarinet",
    "clarinet in a": "clarinet",          # same family; key tracked separately if needed
    "clarinet in b-flat": "clarinet",
    "e-flat clarinet": "eflat_clarinet",
    "eb clarinet": "eflat_clarinet",
    "e♭ clarinet": "eflat_clarinet",
    "bass clarinet": "bass_clarinet",
    "basset horn": "basset_horn",
    "contrabass clarinet": "contrabass_clarinet",
    # bassoon family
    "bassoon": "bassoon",
    "bassoons": "bassoon",
    "contrabassoon": "contrabassoon",
    "double bassoon": "contrabassoon",
    # saxophones
    "soprano saxophone": "soprano_sax",
    "soprano sax": "soprano_sax",
    "alto saxophone": "alto_sax",
    "alto sax": "alto_sax",
    "tenor saxophone": "tenor_sax",
    "tenor sax": "tenor_sax",
    "baritone saxophone": "baritone_sax",
    "baritone sax": "baritone_sax",
    # horn family
    "horn": "horn",
    "horns": "horn",
    "french horn": "horn",
    "french horns": "horn",
    "wagner tuba": "wagner_tuba",
    # trumpet family
    "trumpet": "trumpet",
    "trumpets": "trumpet",
    "piccolo trumpet": "piccolo_trumpet",
    "cornet": "cornet",
    "flugelhorn": "flugelhorn",
    "bass trumpet": "bass_trumpet",
    # trombone family
    "trombone": "trombone",
    "trombones": "trombone",
    "tenor trombone": "trombone",
    "alto trombone": "alto_trombone",
    "bass trombone": "bass_trombone",
    "contrabass trombone": "contrabass_trombone",
    # tuba family
    "tuba": "tuba",
    "tubas": "tuba",
    "euphonium": "euphonium",
    "cimbasso": "cimbasso",
    # percussion
    "timpani": "timpani",
    "kettledrums": "timpani",
    "percussion": "percussion",
    "snare drum": "percussion",
    "bass drum": "percussion",
    "cymbals": "percussion",
    "triangle": "percussion",
    "tambourine": "percussion",
    "xylophone": "percussion",
    "glockenspiel": "percussion",
    "marimba": "percussion",
    "vibraphone": "percussion",
    "tubular bells": "percussion",
    "chimes": "percussion",
    "tam-tam": "percussion",
    "gong": "percussion",
    "castanets": "percussion",
    "whip": "percussion",
    "ratchet": "percussion",
    "wind machine": "percussion",
    "thunder machine": "percussion",
    "crotales": "percussion",
    "guiro": "percussion",
    "güiro": "percussion",
    "claves": "percussion",
    "cowbell": "percussion",
    "woodblock": "percussion",
    "wood block": "percussion",
    "slapstick": "percussion",
    "flexatone": "percussion",
    "mark tree": "percussion",
    "suspended cymbal": "percussion",
    "crash cymbals": "percussion",
    "hi-hat": "percussion",
    "snare": "percussion",
    "side drum": "percussion",
    "tenor drum": "percussion",
    "field drum": "percussion",
    "military drum": "percussion",
    "bongos": "percussion",
    "bongo drums": "percussion",
    "congas": "percussion",
    "timbales": "percussion",
    "maracas": "percussion",
    # keyboards
    "piano": "piano",
    "celesta": "celesta",
    "harpsichord": "harpsichord",
    "organ": "organ",
    "harmonium": "harmonium",
    "synthesizer": "synthesizer",
    "synthesizers": "synthesizer",
    # harp / plucked
    "harp": "harp",
    "harps": "harp",
    "guitar": "guitar",
    "mandolin": "mandolin",
    "banjo": "banjo",
    "accordion": "accordion",
    "cimbalom": "cimbalom",
    # strings
    "violin": "violin",
    "violins": "violin",
    "viola": "viola",
    "violas": "viola",
    "cello": "cello",
    "cellos": "cello",
    "violoncello": "cello",
    "violoncellos": "cello",
    "double bass": "double_bass",
    "double basses": "double_bass",
    "contrabass": "double_bass",
    "contrabasses": "double_bass",
    # choir / voices
    "soprano": "soprano",
    "mezzo-soprano": "mezzo_soprano",
    "mezzo soprano": "mezzo_soprano",
    "alto": "alto",
    "contralto": "contralto",
    "tenor": "tenor",
    "baritone": "baritone",
    "bass": "bass_voice",
    "bass-baritone": "bass_baritone",
    "satb chorus": "satb_chorus",
    "satb choir": "satb_chorus",
    "mixed chorus": "satb_chorus",
    "mixed choir": "satb_chorus",
    "children's chorus": "childrens_chorus",
    "boys chorus": "boys_chorus",
    "male chorus": "male_chorus",
    "female chorus": "female_chorus",
}

# Which canonical keys belong to which family
KEY_FAMILY = {
    "piccolo": "flute", "alto_flute": "flute", "bass_flute": "flute",
    "english_horn": "oboe", "oboe_damore": "oboe", "heckelphone": "oboe",
    "eflat_clarinet": "clarinet", "bass_clarinet": "clarinet",
    "contrabass_clarinet": "clarinet", "basset_horn": "clarinet",
    "contrabassoon": "bassoon",
    "wagner_tuba": "horn",
    "piccolo_trumpet": "trumpet", "cornet": "trumpet",
    "flugelhorn": "trumpet", "bass_trumpet": "trumpet",
    "alto_trombone": "trombone", "bass_trombone": "trombone",
    "contrabass_trombone": "trombone",
    "euphonium": "tuba", "cimbasso": "tuba",
}

SAX_KEYS = {"soprano_sax", "alto_sax", "tenor_sax", "baritone_sax"}

VOICE_KEYS = {
    "soprano", "mezzo_soprano", "alto", "contralto",
    "tenor", "baritone", "bass_voice", "bass_baritone",
}

CHORUS_KEYS = {
    "satb_chorus", "childrens_chorus", "boys_chorus",
    "male_chorus", "female_chorus",
}

PERCUSSION_INSTRUMENT_KEYS = {
    "snare drum", "bass drum", "cymbals", "triangle", "tambourine",
    "xylophone", "glockenspiel", "marimba", "vibraphone", "tubular bells",
    "chimes", "tam-tam", "gong", "castanets", "whip", "ratchet",
    "wind machine", "thunder machine", "crotales",
}

KEYBOARD_KEYS = {"piano", "celesta", "harpsichord", "organ", "harmonium", "synthesizer"}
EXTRA_KEYS = {"guitar", "electric_guitar", "bass_guitar", "mandolin", "banjo",
              "accordion", "cimbalom", "harp"}
