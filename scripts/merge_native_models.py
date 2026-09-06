"""Merge this computer's native GPT metadata into its custom desktop catalog."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil


def merge(native, custom):
    originals = [m for m in native['models']
                 if m['slug'].startswith('gpt-') or m['slug'] == 'codex-auto-review']
    if not any(m.get('visibility') == 'list' for m in originals):
        raise ValueError('Native model cache has no visible GPT models; refresh native Codex first')
    names = {m['slug'] for m in originals}
    result = {**custom, 'models': originals + [m for m in custom['models'] if m['slug'] not in names]}
    slugs = [m['slug'] for m in result['models']]
    if len(slugs) != len(set(slugs)):
        raise ValueError('Duplicate model IDs in catalog')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, default=Path.home()/'.codex/models_cache.json')
    parser.add_argument('--catalog', type=Path, default=Path.home()/'.codex/cliproxyapi/models.json')
    args = parser.parse_args()
    old = json.loads(args.catalog.read_text())
    new = merge(json.loads(args.native.read_text()), old)
    if new != old:
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = args.catalog.with_name('models.before-native-merge.' + stamp + '.json')
        shutil.copy2(args.catalog, backup)
        backup.chmod(0o600)
        stage = args.catalog.with_suffix('.new')
        with stage.open('w', opener=lambda p, f: os.open(p, f, 0o600)) as out:
            json.dump(new, out, indent=2)
            out.write('\n')
        stage.chmod(0o600)
        os.replace(stage, args.catalog)
    print('Catalog contains native GPT models and existing external models.')


if __name__ == '__main__':
    main()
