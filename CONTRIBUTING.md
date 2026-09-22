<!-- Copyright 2026 Gabriele Pennacchia -->
# Contributing

Use English for issues, pull requests and documentation. Include the Home
Assistant version, Flux version, fan firmware, account region and a small set of
steps to reproduce the problem. Download integration diagnostics from Home
Assistant and review them before attaching them. Never share credentials, tokens,
raw account responses or a Home Assistant backup.

Protocol tests run with Python 3.12 or newer:

```sh
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
```

Framework tests use Home Assistant 2026.9.3 and temporary configuration directories:

```sh
docker run --rm -v "$PWD:/work" -w /work \
  ghcr.io/home-assistant/home-assistant:2026.9.3 \
  python -m unittest discover -s tests_ha -v
```

No test requires real credentials or operates a physical fan. Add regression
coverage for changes to protocol handling, concurrency or recovery. Any new
hardware command must have a verified binding and a precise supported value set.
Do not probe unknown device actions on a user's fan.

Translations live in `custom_components/dreame_mf10_flux/translations`. Copy
`en.json`, translate string values and preserve every key and automation value.
`strings.json` is the English source and must match `translations/en.json`.
Language reviewers are welcome; file completeness does not imply native review.

Brand compositions can be regenerated with `python tools/render_brand.py` after
installing Pillow. Dreame's wordmark remains its owner's trademark; the project
name and compositions identify this unofficial integration.

Maintained by **Gabriele Pennacchia**.
