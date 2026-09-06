"""Exercise private file writes through the actual setup entry points."""
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1]/'scripts'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrivateWritesTest(unittest.TestCase):
    def test_catalog_cli_creates_backup_and_private_file(self):
        module = load('merge_native_models')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            native, catalog = root/'native.json', root/'models.json'
            native.write_text(json.dumps({'models': [{'slug': 'gpt-example', 'visibility': 'list'}]}))
            catalog.write_text(json.dumps({'models': [{'slug': 'external-example'}]}))
            with patch('sys.argv', ['merge', '--native', str(native), '--catalog', str(catalog)]):
                module.main()
            self.assertEqual(len(json.loads(catalog.read_text())['models']), 2)
            self.assertEqual(stat.S_IMODE(catalog.stat().st_mode), 0o600)
            self.assertEqual(len(list(root.glob('models.before-native-merge.*.json'))), 1)

    def test_native_marker_never_contains_credentials(self):
        module = load('enable_native_login')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'.codex').mkdir()
            native = {'auth_mode': 'chatgpt', 'tokens': {'access_token': 'synthetic-access', 'account_id': 'synthetic-account', 'refresh_token': 'synthetic-refresh'}}
            (root/'.codex/auth.json').write_text(json.dumps(native))
            with patch.object(module.Path, 'home', return_value=root):
                module.main()
            marker = root/'.cli-proxy-api/codex-desktop-native.json'
            self.assertNotIn('synthetic-', marker.read_text())
            self.assertTrue(json.loads(marker.read_text())['desktop_native_auth'])
            self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)


if __name__ == '__main__':
    unittest.main()
