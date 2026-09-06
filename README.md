# Codex-harness

讓 Codex 桌面 App 透過本機 CLIProxyAPI 使用 Grok、Gemini、GLM 與 Muse Spark，並處理 context 用量、串流重試及工具格式相容性。

這是目前三台 Apple Silicon Mac 部署的原始碼與操作紀錄。Repository 不包含 API key、OAuth 登入資料、完整桌面工具 schema、私人任務紀錄或編譯執行檔。

| 模型 | 路由 | Thinking | Context / 壓縮門檻 |
|---|---|---|---|
| Grok 4.6 | xAI OAuth | High | 500,000 / 450,000 |
| Gemini 3.8 Flash | Google Antigravity OAuth | High | 1,048,576 / 900,000 |
| GLM 5.3 Flash | OpenCode Go，Chat Completions | High | 1,000,000 / 850,000 |
| Muse Spark 1.3 Contributor | OpenCode Go，Responses | High | 1,048,576 / 900,000 |

Claude 已依此部署的選擇排除。以上容量是部署設定，不是對所有帳號的供應商容量保證。

## 修正內容

- Grok／Muse 的 hosted search 累計 input，不能直接當作當前 context。只在明顯不一致且可可靠估算的文字請求，改用完整請求的保守估算，保留原始 provider usage。
- 暫時性錯誤冷卻由 60 秒改為 5 秒，配合有限重試；Muse 串流尚未送出生成項目時的暫時性錯誤，可由代理恢復。
- 還原 Muse 的 `namespace.function` 工具名稱，修正完成呼叫及已處理歷史的空白 arguments。
- Muse 的 Gmail 遞迴 schema 使用限定範圍的相容性 override；工具端仍驗證實際參數。
- 診斷僅記錄模型、狀態碼、結構大小和數字用量。
- 原生 GPT 清單從該機 Codex 模型資料合併，保留各模型的 Thinking、容量和顯示設定；安裝前檢查是否遺失 GPT。
- 可選的原生登入參照每次請求讀取該機現有的 ChatGPT access token，登入更新仍由 Codex 負責，不複製或輪替 refresh token。

Context 修正預設只對 `grok-4.6`、`muse-spark-1.3-contributor` 生效，並要求服務設定 `CODEX_DESKTOP_COMPAT=1`。Gemini／GLM 不套用這項特殊用量改寫。

## 建置

需要 Git、Go 1.26+；已部署版本以 Go 1.27.1 建置。

```bash
./scripts/build.sh
```

可用 `GO_BIN=/absolute/path/to/go` 指定 Go。腳本取得 CLIProxyAPI `v7.2.150`，驗證 commit `c77b13694318b0897f2c74104ef48aebdf8c34d6`，套用 patch、執行受影響範圍的測試並編譯至 `build/cliproxyapi-desktopfix1`。不會變更正在運作的服務。

## 設定與安裝

此版本的 installer 是**既有 macOS 部署升級工具**，不是一鍵建立新帳號。需要已安裝 Homebrew CLIProxyAPI、完成各供應商授權，且四個模型已在本機設定中可用。範本位於 [config/](config/)；替換 placeholder 並合併既有設定，不要把範本直接覆蓋到正式檔案。

- 代理設定：`/opt/homebrew/etc/cliproxyapi.conf`。
- Codex 設定：`~/.codex/config.toml`。
- 模型目錄：`~/.codex/cliproxyapi/models.json`。範本只有四個額外模型；合併時保留原有 GPT entries。
- OpenCode Go key 僅存在本機私有設定中。各台 xAI／Antigravity OAuth 各自完成，不經 repository 同步登入資料。
- 必要時執行 `python3 scripts/apply_context_limits.py` 更新已有模型的容量。
- 尚未加入 Muse schema override 時，可執行 `python3 scripts/fix_muse_schema.py`。此程式遇到既有 payload 規則會停止，需先人工合併。

完成設定並建置後：

```bash
python3 scripts/install_macos.py build/cliproxyapi-desktopfix1
python3 scripts/health.py
```

Installer 會備份設定、停用 Homebrew 舊服務，改由 `com.peter.codex-model-proxy` LaunchAgent 執行私有 binary，保留 `127.0.0.1:8317`。模型目錄沒有更動時，不必重開 Codex App。新安裝或修改模型目錄後，應重新載入 Codex。

每次安裝的私有備份目錄都有 `rollback.py`，以 Python 執行即可恢復備份的 proxy 設定並啟動 Homebrew 服務。不要同時啟用兩套服務。後續升級上游需重新檢查 patch，不能把一般 Homebrew upgrade 當成本修正版的升級程序。

## 保留原生 GPT

先執行 `python3 scripts/merge_native_models.py`，將本機 `~/.codex/models_cache.json` 的原生 GPT 資料合併到自訂清單。此操作有備份，四個外接模型設定會保留。模型清單在 Codex 啟動時載入，變更後需重新載入 App。

GPT 還需要可用的代理路由。若此代理尚未另外完成 Codex OAuth，請在升級至包含原生登入修正的 binary 後執行 `python3 scripts/enable_native_login.py`。它只建立 `~/.cli-proxy-api/codex-desktop-native.json` 的參照標記；服務需有 `CODEX_DESKTOP_COMPAT=1`。每次 GPT 請求使用本機 `~/.codex/auth.json` 的最新 access token，絕不把 refresh token 交給代理刷新。登出或失去登入資料時請求會失敗，應在該機重新登入 Codex。此功能限檔案形式的 ChatGPT 登入，並非通用的 Keychain 登入整合。

原生帳號提供、但代理上游模型表遺漏的 GPT，會從該機原生模型 cache 補入路由。這不增加帳號權限，最終可用性仍由 OpenAI 判定。驗證時必須同時檢查 Codex `model/list` 和一個實際 GPT 回覆，不能只檢查外接模型。

取消原生登入參照可刪除上述參照標記。這不影響 Codex 自己的登入；自訂清單如需還原，可使用合併前的 `models.before-native-merge.*.json` 備份。

## 驗證

```bash
python3 -m unittest discover -s tests -p 'test_model_catalog.py'

# Native Codex + fake upstream: no provider credentials used.
python3 tests/integration.py
INJECT_FAILURE=sse python3 tests/integration.py

# Real providers: consumes provider quota.
python3 tests/native_gpt.py gpt-5.4-mini
python3 tests/native_live.py muse-spark-1.3-contributor
python3 tests/native_live.py grok-4.6
```

這些桌面回歸測試需要本機私有的 `~/.codex/cliproxyapi/models.json` 與 `desktop-tools-schema.json`。完整工具 fixture 沒有收錄，以避免散布已連接 App 的詳細資料。沒有這些檔案仍可執行 build script 的 Go 單元測試。原生 Codex binary 預設位於 `/Applications/ChatGPT.app/Contents/Resources/codex`，可用 `CODEX_APP_BINARY` 覆寫；合成測試的 proxy binary 可用 `HARNESS_BINARY` 覆寫。

2026-09-05 三台正式服務驗證：Grok 六輪搜尋零誤壓縮，Muse 九輪工具往返完成，四模型基本呼叫共十二項通過。HomeMac 的 Muse 兩次漏填參數被工具拒絕後，模型成功修正並繼續。[驗證摘要](docs/verification-2026-09-05.json)。

## 用量與限制

Codex 的 context 顯示可能是保守估算，不等同於供應商帳單。原始值保留在 `response.provider_usage`；正規化摘要在 `~/.codex/cliproxyapi/harness-diagnostics.jsonl`，檔案權限 600、5 MB 輪替。

真正過長的對話仍會壓縮。圖片、隱藏歷史等不能可靠估算的請求不扣減；供應商持續故障、額度限制或其他模型錯誤仍可能使請求失敗。這些有限測試不是長時間零錯誤保證。

## 來源

- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)，保留其 [MIT license](third_party/CLIProxyAPI-LICENSE)。本專案不是 OpenAI、xAI 或 OpenCode 官方產品。
- [xAI hosted tool 用量語義](https://docs.x.ai/developers/tools/tool-usage-details)。
- [OpenCode Go](https://opencode.ai/docs/go/)。

提交前執行 `python3 scripts/check_secrets.py --staged`。`work/`、`outputs/`、`build/` 是忽略的本機資料，請勿 force-add。
