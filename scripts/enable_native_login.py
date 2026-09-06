"""Enable the desktop patch's use of the current computer's native Codex login.

Install the patched build first. No OAuth credentials are copied or refreshed.
"""
import json
import os
from pathlib import Path


def main():
    home = Path.home()
    native = json.loads((home/'.codex/auth.json').read_text())
    tokens = native.get('tokens') or {}
    if native.get('auth_mode') != 'chatgpt' or not all(tokens.get(k) for k in ('access_token', 'account_id')):
        raise SystemExit('Sign in to native Codex on this computer first.')
    folder = home/'.cli-proxy-api'
    folder.mkdir(mode=0o700, exist_ok=True)
    marker = folder/'codex-desktop-native.json'
    data = {'type': 'codex', 'auth_kind': 'oauth', 'desktop_native_auth': True,
            'label': 'Native Codex login'}
    if marker.exists():
        current = json.loads(marker.read_text())
        if current != data:
            raise SystemExit('Native marker already exists with different settings; inspect before replacing.')
    else:
        with marker.open('x', opener=lambda p, f: os.open(p, f, 0o600)) as out:
            json.dump(data, out)
            out.write('\n')
    marker.chmod(0o600)
    print('Enabled native login reference. No OAuth credentials copied.')


if __name__ == '__main__':
    main()
