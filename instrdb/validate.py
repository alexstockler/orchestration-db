#!/usr/bin/env python3
"""Validate work-entry data files.

For each YAML file under data/:
  1. validate against schema/work.schema.json
  2. assert entry['formula'] == render(parse-from-structured instrumentation)
  3. assert the formula round-trips: render(parse(formula)) == formula

Usage: python -m instrdb.validate [data_dir]
"""
import json
import os
import sys

import yaml
from jsonschema import Draft202012Validator

from . import Instrumentation, render, parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_schema():
    with open(os.path.join(ROOT, "schema", "work.schema.json")) as fh:
        return json.load(fh)


def validate_entry(entry, validator=None):
    """Validate one entry dict. Returns a list of human-readable problems."""
    if validator is None:
        validator = Draft202012Validator(load_schema())
    problems = []
    for e in validator.iter_errors(entry):
        loc = "/".join(str(p) for p in e.path) or "(root)"
        problems.append(f"schema: {loc}: {e.message}")
    if "instrumentation" in entry and "formula" in entry:
        inst = Instrumentation.from_obj(entry["instrumentation"])
        generated = render(inst)
        if generated != entry["formula"]:
            problems.append(
                f"formula mismatch: file has {entry['formula']!r}, "
                f"render() gives {generated!r}")
        if render(parse(entry["formula"])) != entry["formula"]:
            problems.append("formula does not round-trip through parse()")
    return problems


def validate_dir(data_dir):
    validator = Draft202012Validator(load_schema())
    errors = 0
    files = sorted(f for f in os.listdir(data_dir) if f.endswith((".yaml", ".yml")))
    for fname in files:
        path = os.path.join(data_dir, fname)
        with open(path) as fh:
            entry = yaml.safe_load(fh)
        problems = validate_entry(entry, validator)
        if problems:
            errors += 1
            print(f"[FAIL] {fname}")
            for p in problems:
                print(f"    {p}")
        else:
            print(f"[ok]   {fname}  =>  {entry.get('formula','')}")
    print(f"\n{len(files) - errors}/{len(files)} files valid")
    return errors


if __name__ == "__main__":
    data = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data")
    sys.exit(1 if validate_dir(data) else 0)
