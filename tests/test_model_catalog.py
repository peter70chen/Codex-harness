"""Regression: external model installation must preserve the native GPT picker."""
import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('merge_native_models', Path(__file__).resolve().parents[1]/'scripts/merge_native_models.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CatalogTest(unittest.TestCase):
    def test_preserves_native_metadata_and_external_settings(self):
        native = {'models': [{'slug': 'gpt-example', 'visibility': 'list',
                             'supported_reasoning_levels': ['low', 'high'], 'context_window': 123456}]}
        extra = {'slug': 'external-example', 'default_reasoning_level': 'high'}
        custom = {'models': [extra, {'slug': 'gpt-example', 'context_window': 1}]}
        result = module.merge(native, custom)
        self.assertEqual(result['models'], native['models'] + [extra])
        self.assertEqual(module.merge(native, result), result)
        self.assertEqual(custom['models'][1]['context_window'], 1)

    def test_rejects_empty_native_catalog(self):
        with self.assertRaises(ValueError):
            module.merge({'models': []}, {'models': []})

    def test_keeps_hidden_native_entries_hidden(self):
        native = {'models': [{'slug': 'gpt-example', 'visibility': 'list'},
                             {'slug': 'gpt-hidden', 'visibility': 'hide'}]}
        self.assertEqual(module.merge(native, {'models': []})['models'], native['models'])


if __name__ == '__main__':
    unittest.main()
