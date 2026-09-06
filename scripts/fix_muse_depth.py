"""Bound inline tool schemas for Muse's 10-level limit using scoped payload rules.

Only model-facing boundary schemas are relaxed. The actual tool retains its
original schema and must validate arguments before executing. No tools removed.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re

BEGIN = '# BEGIN MUSE DEPTH COMPATIBILITY'
END = '# END MUSE DEPTH COMPATIBILITY'


def boundaries(schema, path='', depth=1):
    if not isinstance(schema, dict):
        return []
    children = []
    for key in ('properties', 'patternProperties', 'dependentSchemas'):
        for name, child in (schema.get(key) or {}).items():
            escaped = name.replace('\\', '\\\\').replace('.', '\\.').replace('*', '\\*').replace('?', '\\?')
            children.append((path+'.'+key+'.'+escaped, child))
    for key in ('items', 'additionalProperties', 'contains', 'not', 'if', 'then', 'else'):
        if isinstance(schema.get(key), dict):
            children.append((path+'.'+key, schema[key]))
    for key in ('allOf', 'anyOf', 'oneOf', 'prefixItems'):
        for i, child in enumerate(schema.get(key) or []):
            children.append((path+'.'+key+'.'+str(i), child))
    if depth >= 10 and children:
        # Keep the container type and required keys, while expressing the
        # deeper contract as text. Do not misrepresent this as full validation.
        result = {k: schema[k] for k in ('type', 'required', 'minItems', 'maxItems', 'minProperties', 'maxProperties') if k in schema}
        if schema.get('type') == 'object':
            result['additionalProperties'] = True
        contract = json.dumps(schema, ensure_ascii=False, separators=(',', ':'))
        result['description'] = 'Supply the original JSON value following this schema; the tool validates it when called: '+contract
        return [(path, result)]
    return [row for child_path, child in children for row in boundaries(child, child_path, depth+1)]


def rules(tools):
    result = []
    for namespace in tools:
        for tool in namespace.get('tools', [namespace]):
            if tool.get('type') != 'function':
                continue
            name = json.dumps(tool['name'])
            prefix = ('tools.#(type=="namespace")#.tools.#(name=='+name+')#' if namespace.get('type') == 'namespace' else 'tools.#(name=='+name+')#')
            result.extend((prefix+'.parameters'+path, replacement) for path, replacement in boundaries(tool.get('parameters', {})))
    return result


def update(text, replacements):
    if not replacements:
        return text
    if BEGIN in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1:
            raise ValueError('Ambiguous depth compatibility markers')
        text = re.sub(r'\n*'+re.escape(BEGIN)+r'\n.*?'+re.escape(END)+r'\n?', '', text, flags=re.S).rstrip()+'\n'
    if '# END MUSE SCHEMA COMPATIBILITY' not in text:
        raise ValueError('Expected the existing Muse schema payload block; merge rules manually')
    block = '\n'+BEGIN+'\n    - models:\n        - name: "muse-spark-1.3-contributor"\n          protocol: "codex"\n      params:\n'
    for path, replacement in replacements:
        block += '        '+json.dumps(path)+': '+json.dumps(replacement, ensure_ascii=False)+'\n'
    block += END+'\n'
    # The existing marked payload is the final block in the deployed config.
    before, after = text.split('# END MUSE SCHEMA COMPATIBILITY', 1)
    if after.strip():
        raise ValueError('Unexpected configuration after Muse payload; inspect before merging')
    return before+'# END MUSE SCHEMA COMPATIBILITY\n'+block


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True, help='Private tools-only fixture from the affected desktop request')
    parser.add_argument('--config', type=Path, default=Path('/opt/homebrew/etc/cliproxyapi.conf'))
    args = parser.parse_args()
    replacements = rules(json.loads(args.fixture.read_text()))
    original = args.config.read_text()
    updated = update(original, replacements)
    if updated != original:
        private = Path.home()/'.codex/cliproxyapi'
        backup = private/('proxy.before-muse-depth.'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.conf')
        with open(backup, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as out:
            out.write(original)
        stage = args.config.with_suffix('.depth-new')
        with open(stage, 'w', opener=lambda p, f: os.open(p, f, 0o600)) as out:
            out.write(updated)
        stage.chmod(0o600)
        os.replace(stage, args.config)
    print('Muse schema boundary rules installed:', len(replacements))


if __name__ == '__main__':
    main()
