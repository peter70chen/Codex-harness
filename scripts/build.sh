#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$ROOT/build/upstream"
UPSTREAM_COMMIT=c77b13694318b0897f2c74104ef48aebdf8c34d6
GO_BIN="${GO_BIN:-go}"
mkdir -p "$ROOT/build"
if [ ! -d "$SOURCE/.git" ]; then
  git clone --depth 1 --branch v7.2.150 https://github.com/router-for-me/CLIProxyAPI.git "$SOURCE"
fi
test "$(git -C "$SOURCE" rev-parse HEAD)" = "$UPSTREAM_COMMIT"
if git -C "$SOURCE" apply --check "$ROOT/patches/desktopfix1.patch"; then
  git -C "$SOURCE" apply "$ROOT/patches/desktopfix1.patch"
elif git -C "$SOURCE" apply --reverse --check "$ROOT/patches/desktopfix1.patch"; then
  echo "Patch is already applied."
else
  echo "Upstream working tree differs from the expected patch; inspect build/upstream." >&2
  exit 1
fi
cd "$SOURCE"
"$GO_BIN" test ./internal/runtime/executor/helps -count=1
"$GO_BIN" test ./internal/runtime/executor -run 'TestCodexDesktopNativeAuth|TestCodexExecutor|TestCodex.*Stream|TestXAIExecutor' -count=1
"$GO_BIN" test ./sdk/cliproxy -run 'TestDesktopNativeModels|TestRegisterModelsForAuthCodex' -count=1
"$GO_BIN" test ./sdk/cliproxy/auth -run 'TestManager_MarkResult_Transient|Test.*RetryRound|Test.*Cooldown.*Wait' -count=1
"$GO_BIN" build -ldflags '-X main.Version=7.2.150-desktopfix1' -o "$ROOT/build/cliproxyapi-desktopfix1" ./cmd/server
echo "Built $ROOT/build/cliproxyapi-desktopfix1"
