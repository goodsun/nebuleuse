# Nébuleuse 設計書

**作成日:** 2026-04-24
**ステータス:** 初版（実装前）

---

## 1. 全体像

Nébuleuse は「書き捨てたテキストを潜在空間で繋ぐ」個人用ナレッジプール。
完全にローカルで動き、ファイル1つで持ち運べる所有感を最重視する。

```
┌─────────────────────────────────────────────────────────────┐
│  人間                                                         │
│    │ write (md)                            │ ask (自然言語)   │
│    ▼                                       ▼                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐    │
│  │  raw/    │───▶│  ingest  │───▶│   nebuleuse.db        │    │
│  │  *.md    │    │          │    │  (SQLite vss + FTS5)  │    │
│  └──────────┘    └──────────┘    └──────────────────────┘    │
│                                       ▲          ▲           │
│                                       │ search   │ search    │
│                                       │          │           │
│                              ┌────────┴───┐  ┌───┴────────┐  │
│                              │  neb-search│  │  neb-ask   │  │
│                              │  (CLI)     │  │  (CLI)     │  │
│                              └────────────┘  └───┬────────┘  │
│                                                  │ context   │
│                                                  ▼           │
│                                        ┌─────────────────┐   │
│                                        │ mlx_lm.server   │   │
│                                        │ (Bonsai-8B)     │   │
│                                        └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 2. 環境構成

### 2.1 Python 環境

- **Nébuleuse 専用 venv**：`~/workspace/projects/nebuleuse/.venv`
- ツール：`uv`（高速、`pyproject.toml` ベース）
- 既存の `~/workspace/bonsai-test/venv` は実験用 playground として残す（責務分離）
- **モデル本体は HF cache (`~/.cache/huggingface/hub/`) で全 venv 共有**なので重複なし

### 2.2 主要依存

| パッケージ | 用途 |
|---|---|
| `mlx`, `mlx-lm` | Bonsai-8B 推論サーバー |
| `sqlite-vss` | ベクター検索拡張 |
| `sentence-transformers` or 軽量埋め込みクライアント | 埋め込み生成（multilingual-e5） |
| `httpx` | mlx_lm.server への HTTP クライアント |
| `typer` or `click` | CLI フレームワーク |
| `watchdog` | raw/ の変更監視（任意） |

### 2.3 ディレクトリレイアウト

```
~/nebuleuse/                       # データ格納場所（リポジトリ外）
├── raw/                           # 原本（プレーンテキスト、人間が編集）
│   └── 2026/04/24-bonsai-experiment.md
├── nebuleuse.db                   # SQLite（インデックス、再生成可能）
└── .ingest_state.json             # 取り込み済みファイルの mtime / hash

~/workspace/projects/nebuleuse/    # コードリポジトリ
├── README.md
├── LICENSE
├── pyproject.toml
├── .venv/
├── docs/
│   ├── 2026-04-24-design-dialogue.md
│   └── design.md
├── src/nebuleuse/
│   ├── __init__.py
│   ├── cli.py                     # neb コマンドのエントリポイント
│   ├── ingest.py                  # raw/ → DB
│   ├── search.py                  # ハイブリッド検索 (vss + FTS5 + RRF)
│   ├── ask.py                     # search → LLM
│   ├── embed.py                   # 埋め込み生成
│   ├── llm.py                     # mlx_lm.server クライアント
│   └── db.py                      # SQLite 接続・スキーマ
└── tests/
```

## 3. データモデル（SQLite スキーマ）

### 3.1 テーブル設計

```sql
-- 原本ファイルのメタデータ
CREATE TABLE documents (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,        -- raw/ からの相対パス
    title       TEXT,                        -- md の H1 や frontmatter から
    created_at  TEXT NOT NULL,               -- ISO8601
    updated_at  TEXT NOT NULL,
    mtime       REAL NOT NULL,               -- ファイル mtime（差分検出用）
    hash        TEXT NOT NULL                -- 内容ハッシュ（差分検出用）
);

-- チャンク（埋め込みと全文検索の単位）
CREATE TABLE chunks (
    id           INTEGER PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,           -- 文書内での順序
    content      TEXT NOT NULL,
    char_start   INTEGER NOT NULL,
    char_end     INTEGER NOT NULL,
    UNIQUE(document_id, chunk_index)
);

-- 全文検索（FTS5 仮想テーブル）
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    content,
    content='chunks',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'  -- 日本語対応の検討余地あり
);

-- ベクター検索（sqlite-vss 仮想テーブル）
CREATE VIRTUAL TABLE chunks_vss USING vss0(
    embedding(1024)                          -- multilingual-e5-large は 1024 次元
);
```

### 3.2 同期戦略

- `chunks_fts` / `chunks_vss` は `chunks` への INSERT/UPDATE/DELETE トリガーで自動同期
- 取り込み時、ファイルの `(mtime, hash)` を `documents` と比較し、変化があったチャンクのみ再生成
- ファイル削除時は `documents.path` 不在を検出して CASCADE 削除

## 4. インジェスト

### 4.1 フロー

```
1. raw/ を再帰スキャン（*.md）
2. 各ファイルについて (mtime, hash) で変更検出
3. 変更があれば:
   a. 既存の chunks を削除
   b. テキストをチャンク分割（後述）
   c. 各チャンクの埋め込みを生成
   d. chunks / chunks_fts / chunks_vss に INSERT
4. 削除されたファイルがあれば documents から削除
```

### 4.2 チャンク戦略

- 単位：見出し（H1/H2/H3）境界を尊重しつつ、最大 512 文字程度
- オーバーラップ：50 文字（境界での文脈断絶を緩和）
- frontmatter（`---` で囲まれた YAML）はメタデータとして抽出、本文に含めない

### 4.3 埋め込みモデル

- 第一候補：`intfloat/multilingual-e5-large`（1024 次元、日本語含む 100 言語対応、性能良）
- 第二候補：`intfloat/multilingual-e5-small`（384 次元、軽量、Mac mini ローカル向き）
- 実装：`sentence-transformers` 経由、もしくは MLX ネイティブ実装があればそれ

E5 系は入力に prefix が必要：
- インデックス側：`"passage: " + chunk_text`
- クエリ側：`"query: " + user_query`

## 5. 検索

### 5.1 ハイブリッド検索（RRF 統合）

```
入力: query (自然言語)
1. クエリの埋め込みを生成
2. 並列実行:
   a. vss: SELECT id FROM chunks_vss WHERE vss_search(...) LIMIT K
   b. fts: SELECT id FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT K
3. RRF (Reciprocal Rank Fusion) でスコア統合:
   score(d) = sum(1 / (k + rank_i(d)))   k=60 が定番
4. 上位 N 件のチャンクを返す（document 情報を JOIN）
```

### 5.2 全文検索のクエリ整形

- 日本語の場合、FTS5 のデフォルト tokenizer では分かち書きが弱い
- 対策案：
  - **A:** `unicode61` のまま使い、N-gram 風の前処理を Python 側で行う
  - **B:** `signal-fts5-tokenizer` や `simple` tokenizer を試す
  - **C:** 完全な日本語対応が必要になった段階で `pgroonga` への移行を検討
- 初版は **A** で進め、不足を実測してから改善する

### 5.3 K と最終件数

- 各検索の中間 K：50（RRF 統合のためのプール）
- 最終返却件数：10（neb-ask 時は LLM コンテキストの制約から 5〜8 に絞る）

## 6. 回答生成（neb-ask）

### 6.1 フロー

```
1. ユーザーの質問を受け取る
2. neb-search を内部呼び出し（上位 5〜8 件取得）
3. プロンプト構築:
   - System: "あなたは個人ナレッジを参照して回答するアシスタント..."
   - Context: 検索結果のチャンク（出典付き）
   - User: 質問
4. mlx_lm.server に POST（OpenAI 互換 /v1/chat/completions）
5. ストリーミングで端末に出力
6. 末尾に出典（document path + chunk_index）を表示
```

### 6.2 LLM 起動方式

- **常駐サーバー方式** を採用：`mlx_lm.server --model prism-ml/Bonsai-8B-mlx-1bit --port 8080`
- launchd で常駐化を検討（マシン起動時自動起動）
- CLI からは `httpx` で叩くだけ。レイテンシ最小、初回の重みロードを毎回避けられる

### 6.3 エスカレーション（将来）

- ローカル Bonsai-8B で品質不足な質問は、RunPod 上の llm-jp-4 に流す
- 判定はシンプルに `--remote` フラグ手動切替から始める。自動ルーティングは後

## 7. CLI 設計

```
neb ingest                      # raw/ をスキャンして DB を更新
neb search "牧口"               # ハイブリッド検索結果を表示
neb ask "創価学会の創立について" # 検索 → LLM 回答
neb stats                       # 文書数、チャンク数、DB サイズなど
neb serve                       # mlx_lm.server を立ち上げ（薄いラッパー）
```

各コマンドの実装ファイル対応：
- `cli.py` で typer の sub-command 定義、各実装モジュールに委譲

## 8. 実装フェーズ

最小動作までを最優先する。

### Phase 1：MVP（最初の動作確認）
- [ ] pyproject.toml + uv セットアップ
- [ ] `db.py`：スキーマ初期化
- [ ] `embed.py`：multilingual-e5 で埋め込み生成
- [ ] `ingest.py`：素朴な実装（差分検出なし、毎回全更新）
- [ ] `search.py`：vss + FTS5 + RRF
- [ ] `cli.py`：`neb ingest` / `neb search`
- [ ] サンプル md を 5〜10 本書いて検索が成立することを確認

### Phase 2：ask 統合
- [ ] `llm.py`：mlx_lm.server クライアント
- [ ] `ask.py`：プロンプト構築 + 呼び出し
- [ ] `cli.py`：`neb ask`
- [ ] launchd で `mlx_lm.server` 常駐化

### Phase 3：運用品質
- [ ] 差分インジェスト（mtime + hash）
- [ ] frontmatter / 見出し抽出
- [ ] 日本語 FTS5 の改善（N-gram 前処理）
- [ ] watchdog による自動 ingest

### Phase 4（任意・将来）
- [ ] iOS Shortcuts からの書き込み（Mac mini に POST）
- [ ] 音声入力（Whisper ローカル → ingest）
- [ ] エージェンティックループ（LLM が再検索を判断）
- [ ] Web UI（chat 形式）

## 9. 設計上の意思決定ログ

| 決定 | 採用 | 理由 |
|---|---|---|
| ストレージ | SQLite 一本 | ファイル1個の所有感、ベクター + 全文を1クエリで統合可能 |
| 埋め込み | multilingual-e5-large | 多言語性能と次元のバランス。MLX 化されていれば差し替え |
| LLM | Bonsai-8B (MLX) | 1.2GB、Apple Silicon ネイティブ、常駐コスト低 |
| LLM 起動 | mlx_lm.server 常駐 | レイテンシ最小、OpenAI 互換 API で疎結合 |
| venv | Nébuleuse 専用 | bonsai-test との責務分離。モデル本体は HF cache 共有なので重複なし |
| データ場所 | `~/nebuleuse/`（リポジトリ外） | コードとデータの分離、git で個人ノートを追わない |
| 原本管理 | プレーンテキスト固定 | DB 破損・乗り換え時の保険、人間がいつでも読める |

## 10. 非目標（やらないこと）

明示的にスコープ外とすることで、ツール作りの目的化を避ける。

- グラフビュー（Obsidian 的な可視化）
- リッチテキストエディタ
- マルチユーザー対応
- クラウド同期（必要なら git や iCloud で raw/ だけ同期する）
- プラグイン機構
- WebSocket / リアルタイム共同編集

これらが本当に必要になったときは、Nébuleuse 本体ではなく外部ツールとの連携で解決する。
