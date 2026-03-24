# battle-assistant-sv-main + pokechamp 統合版 README（Windows 本番向け）

この README は、**既存の battle-assistant-sv-main** と **既存の pokechamp** を統合した実行環境（`main/`）を、  
Windows で実運用するための **完全手順書** です。

---

## 0. 何が追加され、何を差し替えるか（最重要）

## 0.1 新規で配置するファイル（`main/`）

以下は新規追加ファイルです。`<repo-root>/main/` に置きます。

- `main/__init__.py`
- `main/app.py`（HTTP + WebSocket ランタイム）
- `main/engine.py`（統合解析エンジン）
- `main/index.html`（ランチャーページ）
- `main/integration.js`（battle-assistant UI への統合パネル注入）
- `main/integration.css`（統合パネルスタイル）
- `main/run_windows.bat`（Windows 起動バッチ）
- `main/WINDOWS_PRODUCTION_RUNBOOK.md`（運用手順）
- `main/README.md`（このファイル）

## 0.2 既存で「差し替え（編集）」するファイル

既存の battle-assistant 側は **2ファイルのみ編集** します。

- `battle-assistant-sv-main/index.html`
  - `integration.css` の `<link>` 追加
  - `integration.js` の `<script>` 追加
- `battle-assistant-sv-main/js/index.js`
  - `getIntegrationSnapshot()` 追加
  - `window.pbaApp` / `pba-ready` 公開追加

## 0.3 新規テストファイル

- `tests/test_main_integration_engine.py`

---

## 1. 全ディレクトリ構造（既存 + 追加）

> 実運用で意識すべき範囲に絞って、既存ディレクトリも含めて記載します。

```text
<repo-root>/
├─ battle-assistant-sv-main/               # 既存: キャプチャ/OCR/ダメージ表示フロントエンド
│  ├─ index.html                           # 既存編集対象（integration.css/js を読み込む）
│  ├─ manager.html
│  ├─ setting.html
│  ├─ usage.html
│  ├─ pokemon_view.html
│  ├─ css/
│  │  ├─ index.css
│  │  ├─ common.css
│  │  └─ ...
│  ├─ js/
│  │  ├─ index.js                          # 既存編集対象（snapshot APIを公開）
│  │  ├─ pokemon.js
│  │  ├─ common.js
│  │  ├─ opencv.js
│  │  ├─ tesseract.min.js
│  │  └─ ...
│  ├─ data/
│  │  ├─ battle_data/
│  │  ├─ foreign_name.txt
│  │  └─ ...
│  └─ img/
│
├─ pokechamp/                              # 既存: LLMプレイヤー/探索ロジック
│  ├─ llm_player.py
│  ├─ ollama_player.py
│  └─ ...
│
├─ bayesian/                               # 既存: Bayesian予測
│  ├─ pokemon_predictor.py
│  └─ ...
│
├─ tests/
│  ├─ test_main_integration_engine.py      # 新規
│  └─ ...
│
├─ main/                                   # 新規: 統合ランタイム一式
│  ├─ __init__.py
│  ├─ app.py
│  ├─ engine.py
│  ├─ index.html
│  ├─ integration.js
│  ├─ integration.css
│  ├─ run_windows.bat
│  ├─ WINDOWS_PRODUCTION_RUNBOOK.md
│  └─ README.md
│
├─ pyproject.toml
├─ requirements.txt
└─ ...
```

---

## 2. 既存ファイル差し替え内容（明示）

## 2.1 `battle-assistant-sv-main/index.html`

### 追加するもの（head）

```html
<link rel="stylesheet" href="/main/integration.css">
```

### 追加するもの（body末尾）

```html
<script src="/main/integration.js" type="module"></script>
```

## 2.2 `battle-assistant-sv-main/js/index.js`

### 追加するもの

- `PokemonBattleAssistant` に `getIntegrationSnapshot()` メソッドを追加
- main 初期化部で:
  - `window.pbaApp = app;`
  - `window.dispatchEvent(new CustomEvent('pba-ready', ...));`

---

## 3. 実行前の前提ソフト（Windows）

1. **Python 3.10+**
2. **uv**（依存導入に使用）
3. **Ollama (Windows)**
4. キャプチャーボードドライバ（必要ならメーカー提供）

---

## 4. 省略なしセットアップ手順（初回）

以下は PowerShell の例です。

## 4.1 リポジトリ配置

```powershell
git clone <YOUR_REPO_URL> C:\Pokemon
cd C:\Pokemon
```

## 4.2 Python依存導入

```powershell
uv sync
```

## 4.3 Ollamaインストール確認

```powershell
ollama --version
```

## 4.4 モデル取得（必須）

```powershell
ollama pull llama3.1:8b
```

## 4.5 モデルが入っているか確認

```powershell
ollama list
```

---

## 5. Ollama 接続方法（手取り足取り）

統合エンジンは `pokechamp/ollama_player.py` の既定で  
`http://localhost:11434` に接続します。  
したがって、Ollama サーバがローカルで起動している必要があります。

## 5.1 接続確認コマンド

```powershell
curl http://127.0.0.1:11434/api/tags
```

期待: JSON でモデル一覧が返る。

## 5.2 よくある失敗

- 接続拒否: Ollamaが起動していない
- モデル無し: `ollama pull ...` 未実施
- タイムアウト: 初回ロード中（しばらく待つ）

---

## 6. 起動手順（毎回）

## 6.1 方法A（推奨）: バッチ起動

```bat
cd /d C:\Pokemon
main\run_windows.bat
```

## 6.2 方法B: 手動起動

```powershell
cd C:\Pokemon
uv run python -m main.app --host 127.0.0.1 --http-port 8080 --ws-port 8765 --ollama-model llama3.1:8b
```

---

## 7. 画面操作手順（実運用）

1. ブラウザで `http://127.0.0.1:8080/` を開く  
2. ランチャーから「統合バトルアシスタントを起動」  
3. `battle-assistant-sv-main` UI が開く  
4. 右側に統合パネル（PokéChamp × battle-assistant）が表示される  
5. キャプチャ映像が認識されると、統合パネルが状態更新・提案表示

---

## 8. 運用チェックリスト（試合前）

- [ ] キャプチャーデバイスが選択できる
- [ ] 対戦画面が battle-assistant に映る
- [ ] 統合パネルが表示される
- [ ] ステータスが「中間器接続済み」
- [ ] `Ollama model` に想定モデル名が表示
- [ ] 推奨手が更新される

---

## 9. 障害時の即時対応

## 9.1 Webが開かない

```powershell
netstat -ano | findstr :8080
```

## 9.2 統合パネルが接続エラー

```powershell
netstat -ano | findstr :8765
```

## 9.3 Ollama応答なし

```powershell
curl http://127.0.0.1:11434/api/tags
ollama list
```

必要なら:

```powershell
ollama pull llama3.1:8b
```

---

## 10. モデル切替方法

## 10.1 手動起動で切替

```powershell
uv run python -m main.app --ollama-model qwen2.5
```

## 10.2 バッチで切替

```powershell
set OLLAMA_MODEL=qwen2.5
main\run_windows.bat
```

---

## 11. 更新手順（本番保守）

```powershell
cd C:\Pokemon
git pull
uv sync
pytest -q tests/test_main_integration_engine.py
uv run python -m main.app --help
```

---

## 12. 参考ドキュメント

- `main/WINDOWS_PRODUCTION_RUNBOOK.md`  
  → 障害対応・ロールバック・セキュリティ運用を詳細化した運用手順書。

