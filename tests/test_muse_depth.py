import copy
import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
import json
import stat

spec = importlib.util.spec_from_file_location('depth', Path(__file__).resolve().parents[1]/'scripts/fix_muse_depth.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MuseDepthTest(unittest.TestCase):
    def test_only_overdeep_boundary_changes(self):
        schema = {'type': 'string'}
        for _ in range(10):
            schema = {'type': 'object', 'properties': {'child': schema}, 'required': ['child'], 'additionalProperties': False}
        original = copy.deepcopy(schema)
        replacements = module.boundaries(schema)
        self.assertEqual(len(replacements), 1)
        path, replacement = replacements[0]
        self.assertEqual(path.count('.properties.child'), 9)
        self.assertEqual(replacement['required'], ['child'])
        self.assertTrue(replacement['additionalProperties'])
        self.assertIn('"child":{"type":"string"}', replacement['description'])
        self.assertEqual(schema, original)
        self.assertEqual(module.boundaries({'type': 'object', 'properties': {'child': {'type': 'string'}}}), [])

    def test_cli_writes_private_backup_and_preserves_other_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home/'.codex/cliproxyapi').mkdir(parents=True)
            schema = {'type': 'string'}
            for _ in range(10):
                schema = {'type': 'object', 'properties': {'child': schema}}
            fixture = home/'tools.json'
            fixture.write_text(json.dumps([{'type': 'function', 'name': 'probe', 'parameters': schema}]))
            config = home/'proxy.conf'
            original = 'payload:\n  override:\n    - models: []\n      params: {}\n# END MUSE SCHEMA COMPATIBILITY\n'
            config.write_text(original)
            with patch.object(module.Path, 'home', return_value=home), patch('sys.argv', ['depth', '--fixture', str(fixture), '--config', str(config)]):
                module.main()
            self.assertTrue(config.read_text().startswith(original))
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
            backup = next((home/'.codex/cliproxyapi').glob('proxy.before-muse-depth.*.conf'))
            self.assertEqual(backup.read_text(), original)
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)

    def test_rule_scope_and_existing_configuration(self):
        original = 'payload:\n  override:\n    - models: []\n      params: {}\n# END MUSE SCHEMA COMPATIBILITY\n'
        updated = module.update(original, [('tools.example.parameters', {'type': 'object'})])
        self.assertTrue(updated.startswith(original))
        self.assertIn('name: "muse-spark-1.3-contributor"', updated)
        self.assertNotIn('name: "gpt-', updated)
        self.assertEqual(module.update(updated, [('tools.example.parameters', {'type': 'object'})]), updated)
        with self.assertRaises(ValueError):
            module.update(original+'unrelated: true\n', [('path', {})])


if __name__ == '__main__':
    unittest.main()
