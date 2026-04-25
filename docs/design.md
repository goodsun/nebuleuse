# Nébuleuse 設計書

**作成日:** 2026-04-24
**最終更新:** 2026-04-25（Phase 1 / 2 / 3 実装完了）
**ステータス:** Phase 1 (capture/ingest/search) + Phase 2 (ask/serve) + Phase 3 (bigram FTS / watch / tests) 動作確認済み

---

## 0. 動機（Why）

Nébuleuse の目的は **「把握可能な外部記憶」** を持つこと。

LLM サービス（Claude Projects・メモリ機能・conversation_search 等）が提供する「自動化された外部記憶」は便利だが、
ユーザー側からは「何が今読まれているか」「なぜこの話題が引き出されたか」「何が消えたか」が見えない。
記憶の境界線がサービス側に握られ、思考の軌跡は要約として返ってきて、当時の生の言葉は失われる。

Nébuleuse はこれに対して、以下を担保する：

- 全ての記憶が **生のテキスト** として `raw/` に残る（書いた通りに、自分の手元に）
- 検索プロセスが **透明**（SQL クエリで何がヒットしたか全部見える）
- インデックスは **使い捨て可能**（原本こそが真実）
- 忘却も **自分で制御**（`rm` すれば本当に消える）
- **完全ローカル**（サービスが終わっても動き続ける）

Claude が提供するのは「便利な外部知能」、Nébuleuse が提供するのは「把握可能な外部記憶」。両者は補完関係。
実際、`raw/` に入る MD の多くは AI との対話を経て結晶化したテキストになることを想定している
（つまり対話を Claude に任せ、結晶を Nébuleuse が持つ）。

詳細は [2026-04-24-why-nebuleuse.md](2026-04-24-why-nebuleuse.md) を参照。

### 設計上の含意

この動機は以下の設計判断に直接響く：

| 動機 | 設計への反映 |
|---|---|
| 把握可能性 | 検索結果に必ず出典（document path + chunk_index）を付ける。SQL クエリは可視化可能 |
| 生のテキストの保存 | 原本 md を絶対に変更しない。frontmatter 自動付与すらしない（人間 / capture 時のみ） |
| 入力源の透明性 | チャンクに `source` メタデータを持たせる（`human` / `dialogue:claude` / `voice:whisper` 等） |
| AI 対話の取り込み | `neb capture` を一級市民として用意。stdin / clipboard / file から摩擦ゼロで raw/ に保存 |
| 自動化との適切な距離 | 自動 ingest は明示起動（watchdog はオプション）。ユーザーが「何がいつ取り込まれたか」を把握できる状態を保つ |

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

-- 原本ファイルの追加カラム（source トラッキング）
-- documents テーブルに以下も含める:
--   source      TEXT,                       -- 'human' | 'dialogue:claude' | 'voice:whisper' | etc.
--   source_meta TEXT                        -- JSON 文字列（モデル名・対話相手・録音時刻等）

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
- **対話 MD の特殊扱い:** `source: dialogue:claude` の文書は既に構造化されている（見出し付き、長文、論理的セクション分け）ので、見出し境界を強く尊重する。会話ターンが残っている場合は「ユーザー発話 / AI 発話」のペアを1チャンクの単位にすることも検討

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
- **実装結果:** Phase 3 で **A** を採用。`tokenize.to_index_text()` が CJK を 2-gram、ASCII を小文字単一トークンに変換し、`chunks_fts` には bigram 化したテキストを格納する。「牧口」のような短い固有名詞でも確実にヒットするようになった

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

- **常駐サーバー方式** を採用：`neb serve`（内部で `python -m mlx_lm server --model <MODEL> --port 8080`）
- 既定モデルは `mlx-community/Llama-3.2-3B-Instruct-4bit`。当初想定の Bonsai-8B (1-bit) は現行 mlx-lm 0.31 が 1-bit 量子化を未サポートだったため変更（実装ノート §11 参照）
- launchd で常駐化を検討（マシン起動時自動起動、未実装）
- CLI からは `httpx` で叩くだけ。レイテンシ最小、初回の重みロードを毎回避けられる
- 小型モデルの反復ループ抑制のため `repetition_penalty=1.15` を mlx-lm 拡張パラメータとして付与

### 6.3 エスカレーション（将来）

- ローカル Bonsai-8B で品質不足な質問は、RunPod 上の llm-jp-4 に流す
- 判定はシンプルに `--remote` フラグ手動切替から始める。自動ルーティングは後

## 7. CLI 設計

```
neb capture [--source SRC] [--title TITLE]  # stdin / clipboard / file から raw/ に保存
neb ingest                                  # raw/ をスキャンして DB を更新
neb search "牧口"                            # ハイブリッド検索結果を表示
neb ask "創価学会の創立について"              # 検索 → LLM 回答
neb stats                                    # 文書数、チャンク数、DB サイズなど
neb serve                                    # mlx_lm.server を立ち上げ（薄いラッパー）
```

### 7.1 `neb capture` の詳細

Nébuleuse の最も重要な入力プリミティブ。AI 対話を結晶として取り込む摩擦をゼロにする。

```bash
# パイプ経由
pbpaste | neb capture --source dialogue:claude --title "Nébuleuse 設計対話"

# ファイル経由
neb capture --source dialogue:claude path/to/conversation.md

# エディタ起動
neb capture                                 # $EDITOR が開いてその場で書く
```

挙動：
1. 入力テキストを受け取る
2. `--title` 未指定なら H1 や先頭行から自動推定、それも無ければ対話的に確認
3. ファイル名 `raw/YYYY/MM/DD-{slug}.md` を生成
4. frontmatter に `source` / `created_at` / `title` を付与
5. 保存後、自動で `neb ingest` を呼ぶ（オプションで抑制可）

### 7.2 実装ファイル対応

- `cli.py` で typer の sub-command 定義、各実装モジュールに委譲

## 8. 実装フェーズ

最小動作までを最優先する。

### Phase 1：MVP（最初の動作確認）✅ 完了
- [x] pyproject.toml + uv セットアップ
- [x] `db.py`：スキーマ初期化（`source` カラムを含む）
- [x] `embed.py`：multilingual-e5 で埋め込み生成
- [x] `ingest.py`：差分検出（mtime + hash）込みで実装、削除検出も
- [x] `search.py`：vss + FTS5 + RRF（出典情報を必ず返す）
- [x] `cli.py`：`neb capture` / `neb ingest` / `neb search` / `neb stats`
- [x] 既存の `docs/2026-04-24-*.md` を `neb capture` で取り込んで検索が成立することを確認（3 docs / 65 chunks）

### Phase 2：ask 統合 ✅ 完了
- [x] `llm.py`：mlx_lm.server クライアント（chat / chat_stream / health）
- [x] `ask.py`：プロンプト構築 + 出典付き回答（コンテキスト 4000 字上限）
- [x] `cli.py`：`neb ask`（ストリーミング既定）/ `neb serve`
- [ ] launchd で `mlx_lm.server` 常駐化（任意）

### Phase 3：運用品質 ✅ 完了
- [x] 差分インジェスト（mtime + hash）— Phase 1 で先行実装済み
- [x] frontmatter / 見出し抽出
- [x] 日本語 FTS5 の改善（bigram 前処理、`tokenize.py`）
- [x] watchdog による自動 ingest（`neb watch`、debounce 1s）
- [x] テスト整備（pytest 15 件、埋め込みはスタブで重いロード回避）

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
| LLM | Llama-3.2-3B-Instruct-4bit (MLX) | 既定。当初想定の Bonsai-8B (1-bit) は §11 のとおり未対応。`NEBULEUSE_LLM_MODEL` で差し替え可 |
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
- **「自動化されすぎた挙動」**：ユーザーが何が起きているか把握できない状態を作らない。サイレントなインジェスト、勝手なメタデータ書き換え、不可視な記憶の選別はやらない（§0 動機より）

これらが本当に必要になったときは、Nébuleuse 本体ではなく外部ツールとの連携で解決する。

---

## 11. 実装ノート

### 11.1 LLM モデル既定の変更（2026-04-25）

設計書の初版では Bonsai-8B (`prism-ml/Bonsai-8B-mlx-1bit`、1-bit 量子化、1.15GB) を既定 LLM として指名していたが、Phase 2 実装中に **現行 mlx-lm 0.31 系は 1-bit 量子化をサポートしていない** ことが判明した（サポートされる bit 数は 2/3/4/5/6/8）。サーバー起動は成功するが、最初のリクエストで以下のエラーで落ちる：

```
ValueError: [quantize] The requested number of bits 1 is not supported.
The supported bits are 2, 3, 4, 5, 6 and 8.
```

設計上 LLM は差し替え可能な前提（`description` も "a local LLM" 抽象化）だったため、既定モデルを `mlx-community/Llama-3.2-3B-Instruct-4bit`（~2GB、4-bit 量子化）に変更し、`NEBULEUSE_LLM_MODEL` 環境変数で他モデルに切り替えられる仕様にした。

将来 mlx-lm が 1-bit 量子化を再サポートした場合、または PrismML が他 bit 版の Bonsai を出した場合は、環境変数を切り替えるだけで Bonsai に戻せる。

### 11.2 反復ループ抑制

Llama-3.2-3B (4bit) のような小型モデルは temperature 0.3 でも同じフレーズを延々と繰り返すループに陥りやすい。`max_tokens=1024` を使い切るまで止まらないため、対策として：

- `max_tokens` の既定を 512 に絞る
- mlx-lm 拡張パラメータの `repetition_penalty=1.15` をリクエストに付与

これで実用的な長さの回答が安定して返るようになった。指示追従性能（出典 `[#N]` の付与など）はモデルサイズ依存なので、品質を求めるなら Qwen2.5-7B-4bit などへ差し替える前提。

### 11.3 ディレクトリ構造（実装済み）

```
src/nebuleuse/
├── __init__.py
├── cli.py        # neb サブコマンド
├── capture.py    # raw/ への保存
├── ingest.py     # raw/ → DB（差分検出込み）
├── chunker.py    # 見出し境界尊重チャンク分割
├── tokenize.py   # 日本語 bigram + ASCII 単語の混合トークナイズ
├── embed.py      # multilingual-e5
├── search.py     # vss + FTS5 (bigram) + RRF
├── ask.py        # search → LLM
├── llm.py        # mlx_lm.server クライアント
├── watch.py      # raw/ 監視 + debounced auto-ingest
└── db.py         # SQLite 接続・スキーマ

tests/            # pytest 15 件
```
