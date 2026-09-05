"""Inspect tracked/staged text without printing any matching secret values."""
from pathlib import Path
import re, subprocess, sys

staged = '--staged' in sys.argv
names = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'] if staged else ['git', 'ls-files', '-z']).split(b'\0')
patterns = {
    'API credential': rb'\bsk-[A-Za-z0-9_-]{20,}',
    'GitHub credential': rb'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})',
    'OAuth access token': rb'\bya29\.[A-Za-z0-9._-]{20,}',
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'private network address': rb'\b[a-z0-9-]+\.tail[a-z0-9]+\.ts\.net\b',
    'embedded credential assignment': rb'(?im)^\s*(?:api-key|experimental_bearer_token|refresh_token|access_token)\s*[:=]\s*["\'](?!REPLACE_|\$|<)[A-Za-z0-9._-]{24,}["\']',
}
issues = []
for raw in names:
    if not raw: continue
    name = raw.decode()
    if name.startswith(('work/', 'outputs/', 'build/')) or name.endswith(('.key', '.pem', '.jsonl')):
        issues.append((name, 'private/generated path'))
        continue
    content = subprocess.check_output(['git', 'show', ':'+name]) if staged else Path(name).read_bytes()
    for label, pattern in patterns.items():
        if re.search(pattern, content): issues.append((name, label))
for name, label in issues: print(f'{name}: {label}')
if issues: raise SystemExit(1)
print('Secret-pattern and private-path checks passed.')
