# Windows本番運用手順書（battle-assistant-sv-main + pokechamp）

本書は、`main/` 統合ランタイムを **Windows実運用** するための手順書です。  
対象は、キャプチャーボード入力を使って `battle-assistant-sv-main` を動作させ、`pokechamp`（Ollama backend）による提案を同一画面に表示する構成です。

---

## 1. 対象構成

- フロントエンド: `battle-assistant-sv-main/index.html`
- 統合ブリッジ: `main/app.py`（HTTP + WebSocket）
- 推論エンジン: `main/engine.py`（Bayesian + Ollama + fallback）
- 統合UI: `main/integration.js` / `main/integration.css`
- Windows起動バッチ: `main/run_windows.bat`

---

## 2. 本番前提（必須）

## 2.1 OS / ハードウェア

- Windows 10/11（64bit）
- キャプチャーボード（UVC準拠推奨）
- ポケモンSV実機（Switch）

## 2.2 ソフトウェア

- Python 3.10 以上
- Ollama（Windows版）
- Git（ソース更新時のみ）
- `uv`（依存管理推奨）

## 2.3 ネットワーク/ポート

- HTTP: `127.0.0.1:8080`
- WebSocket: `127.0.0.1:8765`
- Ollama API: `127.0.0.1:11434`

> すべてローカルホスト運用を前提にしてください（外部公開しない）。

---

## 3. 初期セットアップ（初回のみ）

### 3.1 リポジトリ配置

例: `C:\Pokemon` に配置

```powershell
git clone <your-repo-url> C:\Pokemon
cd C:\Pokemon
```

### 3.2 Python依存導入

```powershell
uv sync
```

### 3.3 Ollamaモデル準備

```powershell
ollama pull llama3.1:8b
```

必要に応じて運用モデルを差し替えてください（例: `qwen2.5`, `gpt-oss:20b`）。

---

## 4. 日次起動手順（標準運用）

## 4.1 Ollama起動確認

```powershell
ollama list
```

`llama3.1:8b` が一覧にあることを確認。

## 4.2 統合ランタイム起動

### 方法A（推奨）: バッチ

```bat
main\run_windows.bat
```

### 方法B: 明示起動

```powershell
uv run python -m main.app --host 127.0.0.1 --http-port 8080 --ws-port 8765 --ollama-model llama3.1:8b
```

## 4.3 画面アクセス

ブラウザで以下を開く:

- `http://127.0.0.1:8080/`（ランチャー）
- 「統合バトルアシスタントを起動」クリック

起動後、右側に統合提案パネルが表示されることを確認。

---

## 5. 本番チェックリスト（対戦開始前）

- [ ] キャプチャーデバイスが OS から見えている
- [ ] battle-assistant画面に映像が表示される
- [ ] 統合パネルが表示される
- [ ] パネルの接続表示が「中間器接続済み」
- [ ] `Ollama model` が想定モデル名で表示
- [ ] 対戦画面で提案が更新される

---

## 6. 監視ポイント（運用中）

## 6.1 正常時

- 接続状態: `中間器接続済み`
- 数秒間隔で `解析完了 (xxxms)` 表示
- 推奨手・候補手ランキングが更新

## 6.2 異常兆候

- `中間器接続エラー`
- `中間器との接続が切断されました`
- 推奨手が長時間更新されない
- 提案が常に `heuristic_fallback` のみ

---

## 7. 障害対応手順

## 7.1 Web UIに接続できない

1. ランタイムプロセス確認
2. ポート確認:
   ```powershell
   netstat -ano | findstr :8080
   netstat -ano | findstr :8765
   ```
3. 再起動:
   - ランタイム停止（Ctrl+C）
   - 再度 `main\run_windows.bat`

## 7.2 Ollama応答不良

1. Ollama API確認:
   ```powershell
   curl http://127.0.0.1:11434/api/tags
   ```
2. モデル再pull:
   ```powershell
   ollama pull llama3.1:8b
   ```
3. それでも失敗する場合:
   - 一時的に fallback 提案で継続
   - 対戦後に `main.app` を再起動

## 7.3 キャプチャー映像が出ない

1. デバイス再接続（USB差し直し）
2. 競合アプリ終了（OBS等）
3. ブラウザ再読み込み
4. 必要時はPC再起動

---

## 8. モデル切り替え運用

### 一時切替

```powershell
uv run python -m main.app --ollama-model qwen2.5
```

### バッチ切替

```powershell
set OLLAMA_MODEL=qwen2.5
main\run_windows.bat
```

---

## 9. 更新運用（メンテナンス）

```powershell
cd C:\Pokemon
git pull
uv sync
```

更新後は必ず以下を確認:

```powershell
uv run python -m main.app --help
pytest -q tests/test_main_integration_engine.py
```

---

## 10. ロールバック

不具合時は直前安定コミットへ戻します。

```powershell
git log --oneline -n 20
git checkout <stable_commit_sha>
uv sync
main\run_windows.bat
```

---

## 11. セキュリティ運用指針

- 本番でも `--host 127.0.0.1` 固定
- ルータ公開・ポート開放はしない
- 外部LAN経由でアクセスさせない
- APIキー不要構成（Ollamaローカル）のまま運用

---

## 12. 本番運用コマンド早見表

```powershell
# 依存導入
uv sync

# モデル準備
ollama pull llama3.1:8b

# 起動
main\run_windows.bat

# 動作確認
curl -I http://127.0.0.1:8080/
```

