# Contributing

One YAML file per work in `data/`, named `<composer-slug>-<work-slug>.yaml`.

Before opening a PR, run the gate locally:

```bash
pip install -r requirements.txt
python tests/test_engine.py     # engine conformance
python -m instrdb.validate      # every data file
```

CI runs the same checks on every push and pull request. A PR is mergeable when:

1. The file validates against `schema/work.schema.json`.
2. `formula` exactly equals `render(instrumentation)`.
3. The formula round-trips through `parse()`.
4. Every instrument name is in the controlled vocabulary (`instrdb/vocab.py`).

Set `provenance.confidence` honestly:
`score_verified` > `multi_source` > `single_source` > `unverified`.
Publisher-scraped entries start at `single_source`; bump to `score_verified`
once you've checked the actual score (e.g. on IMSLP).

See `spec/NOTATION.md` for the notation grammar and `docs/sources-boosey.md`
for the publisher ingestion path.
