"""Conformance tests for the notation engine.

Each case gives a structured instrumentation dict and its expected formula.
We assert render(model) == formula AND render(parse(formula)) == formula.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from instrdb import Instrumentation, render, parse

CASES = {
    # The user's own example — proves the engine reproduces canonical shorthand.
    "user_example": (
        {
            "flute": 2, "oboe": 2, "clarinet": 2, "bassoon": 2,
            "horn": 4, "trumpet": 2, "trombone": 3, "tuba": 1,
            "percussion": {"timpani": 1, "players": 3},
            "keyboards": [{"instrument": "piano", "doublings": ["celesta"]}],
            "harp": 1, "strings": "str",
        },
        "2222 4231 tmp+3 pf/cel hp str",
    ),
    # Simple, no amplifications, missing brass -> 0s.
    "mozart_40": (
        {
            "flute": 1, "oboe": 2, "clarinet": 2, "bassoon": 2,
            "horn": 2, "strings": "str",
        },
        "1222 2000 str",
    ),
    # Amplified woodwinds (doubling + dedicated aux chair); brass stays compact.
    "beethoven_5": (
        {
            "flute": [{}, {"doublings": ["piccolo"]}],
            "oboe": 2, "clarinet": 2,
            "bassoon": [{}, {}, {"instrument": "contrabassoon"}],
            "horn": 2, "trumpet": 2, "trombone": 3,
            "percussion": {"timpani": 1}, "strings": "str",
        },
        "2[1.2/pic] 2 2 3[1.2.cbn] 2230 tmp str",
    ),
    # Choral/orchestral with extra percussion; soloists+chorus are separate fields.
    "beethoven_9": (
        {
            "flute": [{}, {"doublings": ["piccolo"]}],
            "oboe": 2, "clarinet": 2,
            "bassoon": [{}, {}, {"instrument": "contrabassoon"}],
            "horn": 4, "trumpet": 2, "trombone": 3,
            "percussion": {"timpani": 1, "players": 3}, "strings": "str",
            "soloists": ["soprano", "alto", "tenor", "bass"],
            "chorus": ["SATB"],
        },
        "2[1.2/pic] 2 2 3[1.2.cbn] 4230 tmp+3 str",
    ),
    # Mixed woodwind block (one amplified family forces the whole block to space);
    # no timpani, two harps, no brass except horns.
    "debussy_faune": (
        {
            "flute": 3,
            "oboe": [{}, {}, {"instrument": "english_horn"}],
            "clarinet": 2, "bassoon": 2, "horn": 4,
            "percussion": {"players": 1}, "harp": 2, "strings": "str",
        },
        "3 3[1.2.Eh] 2 2 4000 1perc 2hp str",
    ),
    # A string work: no wind/brass block at all, freeform strings + continuo.
    "bach_brandenburg_3": (
        {"strings": {"standard": False, "description": "3vn 3va 3vc",
                     "continuo": True}},
        "3vn 3va 3vc cont",
    ),
}


def run():
    fails = 0
    for name, (obj, expected) in CASES.items():
        inst = Instrumentation.from_obj(obj)
        got = render(inst)
        ok_render = got == expected
        roundtrip = render(parse(expected))
        ok_round = roundtrip == expected
        status = "ok" if (ok_render and ok_round) else "FAIL"
        print(f"[{status}] {name}")
        if not ok_render:
            print(f"    render   expected: {expected!r}")
            print(f"             got:      {got!r}")
        if not ok_round:
            print(f"    roundtrip got:      {roundtrip!r}")
        fails += 0 if (ok_render and ok_round) else 1
    print(f"\n{len(CASES) - fails}/{len(CASES)} passed")
    return fails


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
