"""Locale completeness and stable automation keys. Copyright 2026 Gabriele Pennacchia."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components/dreame_mf10_flux"


def leaves(value, prefix=""):
    if isinstance(value, dict):
        return {key for name, child in value.items() for key in leaves(child, prefix + "." + name)}
    return {prefix}


class LocalizationTests(unittest.TestCase):
    def test_every_locale_has_all_english_keys(self):
        english = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
        self.assertEqual(english, json.loads((ROOT / "translations/en.json").read_text()))
        for path in (ROOT / "translations").glob("*.json"):
            with self.subTest(locale=path.stem):
                translated = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(leaves(english), leaves(translated))
                for value in translated["entity"]["select"]["oscillation"]["state"].values():
                    self.assertTrue(value.strip())
