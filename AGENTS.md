# Codex-harness maintenance

- Keep changes scoped to the desktop proxy integration and its tests.
- Never commit credentials, OAuth files, complete desktop tool fixtures, raw requests, task rollouts, machine-specific private configuration, or personal SSH addresses.
- `work/`, `outputs/`, and `build/` are local-only. Do not force-add them.
- Keep upstream changes in `patches/desktopfix1.patch`; preserve the upstream license and pinned commit.
- For Go patch changes, format the modified Go files, run affected package tests, build the server, and refresh the patch from the pinned upstream source.
- Run `python3 scripts/check_secrets.py --staged` before committing.
- Live tests use provider quota. Prefer synthetic tests for protocol changes, then bounded native tests when integration behavior changed.
- Installation replaces a running local proxy service. Keep backups and rollback instructions; avoid interrupting unrelated active tasks.
