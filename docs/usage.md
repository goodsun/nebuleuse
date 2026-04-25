# Nébuleuse 使い方ガイド

書き捨てのテキストを放り込み、必要なときに引き出すための個人ナレッジプール。
本書はインストールから日常運用までを通しで説明する。設計思想は
[README.md](../README.md) と [design.md](./design.md) を参照。

---

## 1. クイックスタート（5 分）

### 1.1 前提

- macOS（Apple Silicon, arm64）— `mlx` / `mlx-lm` が arm64 必須
- Python 3.11 以上
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 1.2 インストール

```bash
git clone <this-repo> nebuleuse && cd nebuleuse
uv sync                            # .venv 構築 + 依存解決（~2 分）
uv run neb stats                   # 初回起動で ~/nebuleuse/ を自動作成
```

`uv run neb` を毎回叩くのが面倒なら、シェルに以下を加えると `neb` 単独で呼べる：

```bash
alias neb="uv run --project /Users/<you>/workspace/projects/nebuleuse neb"
```

### 1.3 最初のメモを取り込んで検索する

```bash
# テキストを raw/ に放り込む
echo "# テスト\nNébuleuse の動作確認メモ" | uv run neb capture --source human

# DB に取り込む（capture 直後は自動 ingest が走るので通常は不要）
uv run neb ingest

# 検索
uv run neb search "動作確認"
```

ヒットすれば成功。

### 1.4 LLM に質問する

```bash
# シェル A: モデルサーバーを常駐起動（初回はモデル DL ~2GB）
uv run neb serve

# シェル B: 検索 → LLM 回答
uv run neb ask "動作確認メモの内容は？"
```

---

## 2. データ配置

```
~/nebuleuse/                       # NEBULEUSE_HOME（変更可）
├── raw/                           # 原本（プレーンテキスト、自分で編集可）
│   └── 2026/04/25-foo.md
└── nebuleuse.db                   # SQLite（インデックス、再生成可能）
```

**重要な原則:**

- **`raw/` の md が真実**。自分のエディタで自由に編集してよい。Nébuleuse は中身を勝手に書き換えない。
- **`nebuleuse.db` は導出物**。壊れたら `rm` して `neb ingest` で作り直せる。
- **バックアップは `raw/` だけで十分**。`cp -r ~/nebuleuse/raw <somewhere>` か git/iCloud で同期する。

---

## 3. コマンドリファレンス

### `neb capture` — テキストを取り込む

`raw/YYYY/MM/DD-{slug}.md` に frontmatter 付きで保存し、その場で ingest を呼ぶ。

```bash
# パイプ経由
pbpaste | neb capture --source dialogue:claude --title "今日の壁打ち"

# ファイル経由
neb capture --source dialogue:claude path/to/conversation.md

# stdin が TTY の場合はエラー（明示的に file を指定すること）
```

**オプション:**

| フラグ | 既定 | 用途 |
|---|---|---|
| `--source` | なし | `human` / `dialogue:claude` / `voice:whisper` 等のラベル |
| `--title` | 本文先頭 H1 から推定 | frontmatter `title` |
| `--no-ingest` | false | 保存後の自動 ingest をスキップ（バルク取り込み時など） |

**保存される frontmatter 例:**

```yaml
---
title: 今日の壁打ち
created_at: 2026-04-25T10:30:00+09:00
source: dialogue:claude
---
```

### `neb ingest` — DB を更新する

`raw/` を再帰スキャンし、`(mtime, hash)` で差分検出して変更分だけ再チャンク・再埋め込みする。
削除されたファイルも検出して連動削除する。

```bash
neb ingest
# {"added": 0, "updated": 1, "deleted": 0, "chunks": 4}
```

通常は `neb capture` / `neb watch` 経由で勝手に走るので明示呼び出しは不要。
DB を作り直すときは：

```bash
rm ~/nebuleuse/nebuleuse.db && neb ingest
```

### `neb watch` — 自動取り込み

`raw/` を watchdog で監視し、debounce 1 秒で連続変更を 1 回の ingest にまとめる。
エディタで md を直接編集する運用に使う。

```bash
neb watch
# [watch] watching /Users/you/nebuleuse/raw
# [watch] 10:30:01 ingested: {'added': 1, 'updated': 0, 'deleted': 0, 'chunks': 3}
```

Ctrl-C で終了。常駐させたければ `nohup` か後述の launchd プランを参照。

### `neb search` — ハイブリッド検索

ベクター検索（multilingual-e5-large）と全文検索（FTS5 bigram）を RRF (k=60) で統合し、
出典付きで上位ヒットを表示する。

```bash
neb search "把握可能な外部記憶"           # 概念検索（ベクター主導）
neb search "牧口"                        # 短い固有名詞（bigram FTS で確実にヒット）
neb search "siegeNgin" -n 20             # 上位 20 件
neb search "..." --full                  # チャンク全文を表示
```

出力例：

```
[1] score=0.0328  Nébuleuse 設計書
    src: 2026/04/25-design.md#1  (human)
    Nébuleuse の目的は「把握可能な外部記憶」を持つこと。LLM サービスが ...
```

`src` は `relative_path#chunk_index (source)` 形式。`raw/` と組み合わせれば原本に戻れる。

### `neb ask` — LLM に質問

検索結果（既定 6 チャンク、最大 4000 字）を文脈に LLM へ問う。出典番号 `[#N]` 付きで回答が返る。

```bash
# 別シェルで neb serve を起動しておくこと
neb ask "Nébuleuse はなぜ SQLite 一本にしたのか？"
neb ask "..." --no-stream                # 完成回答を一括表示
neb ask "..." -n 3                       # コンテキストチャンク数を絞る
```

サーバー未起動だと `LLM server unreachable` で exit 2。

### `neb serve` — モデルサーバー

`mlx_lm.server` を薄くラップして起動する。前面で動くので Ctrl-C で停止。

```bash
neb serve                                       # 既定 127.0.0.1:8080
neb serve --port 9090
neb serve --model mlx-community/Qwen2.5-7B-Instruct-4bit
```

別モデルを既定にしたければ環境変数 `NEBULEUSE_LLM_MODEL` を設定する。
初回起動時に Hugging Face からモデルをダウンロードする（既定モデルで ~2GB）。

### `neb stats` — 状態確認

```bash
neb stats
# {
#   "documents": 3,
#   "chunks": 65,
#   "db_path": "/Users/you/nebuleuse/nebuleuse.db",
#   "db_size_bytes": 380928
# }
```

---

## 4. 環境変数

| 変数 | 既定 | 用途 |
|---|---|---|
| `NEBULEUSE_HOME` | `~/nebuleuse` | データディレクトリ。複数プロファイル運用に便利 |
| `NEBULEUSE_EMBED_MODEL` | `intfloat/multilingual-e5-large` | 埋め込みモデル（次元 1024 を想定） |
| `NEBULEUSE_LLM_MODEL` | `mlx-community/Llama-3.2-3B-Instruct-4bit` | `neb serve` / `neb ask` 共通 |
| `NEBULEUSE_LLM_URL` | `http://127.0.0.1:8080/v1` | OpenAI 互換 API ベース URL |
| `NEBULEUSE_LLM_TIMEOUT` | `120` | LLM リクエストタイムアウト（秒） |

`.envrc` (direnv) や launchd plist に書き込んで永続化するのが楽。

---

## 5. 典型ワークフロー

### 5.1 AI 対話を結晶として残す

Claude や ChatGPT との対話で「これは残しておきたい」と思ったら：

```bash
pbpaste | neb capture --source dialogue:claude --title "Bonsai 量子化の調べもの"
```

`source: dialogue:claude` をラベルとして残しておくと、後から「対話由来 vs 自筆」の区別がつく
（`raw/` の frontmatter に保存される）。

### 5.2 思いついたことを一行で残す

エディタで `~/nebuleuse/raw/2026/04/25-foo.md` を直接開いて書き、`neb watch` で自動取り込み。

```bash
# 別タブ or ターミナルセッションで常駐
neb watch
```

### 5.3 半年前の自分に問いかける

```bash
neb ask "なぜ Bonsai-8B を採用しなかったのか？"
```

回答中の `[#1]` `[#2]` の番号が末尾の出典リストに対応する。気になる出典があれば
`raw/` の該当ファイルを直接開けばよい（パスが出ているのでクリックで飛べる端末も多い）。

### 5.4 メモを忘却する

```bash
rm ~/nebuleuse/raw/2026/04/25-foo.md
neb ingest                              # DB から自動的に消える
# あるいは neb watch を回しておけば自動で連動
```

`rm` で本当に消える。サービス側に残らない。

---

## 6. トラブルシュート

### `neb ask` が `LLM server unreachable`

`neb serve` を別シェルで起動していない、または `NEBULEUSE_LLM_URL` が違う。
`curl http://127.0.0.1:8080/v1/models` で疎通確認。

### モデル起動時に `1-bit not supported`

mlx-lm 0.31 系は 1-bit 量子化未対応。Bonsai-8B-mlx-1bit などを使いたい場合は
4-bit 系のモデル（既定 Llama-3.2-3B-4bit / Qwen2.5-7B-4bit など）に切り替えるか、
将来 1-bit 対応版の mlx-lm を待つ。

### 検索結果が偏る・出典が同じファイルばかり

- ファイル数が少ないうちは正常（小さい DB ではこうなる）
- それでも気になるなら `-n` を増やす、`--full` で全文を見て妥当性を判定する

### LLM の回答が同じフレーズを繰り返す

小型モデル特有の現象。`repetition_penalty=1.15` を入れているが収まらない場合は
モデル差し替え（`NEBULEUSE_LLM_MODEL`）を検討。

```bash
NEBULEUSE_LLM_MODEL=mlx-community/Qwen2.5-7B-Instruct-4bit neb serve
```

### DB を完全に作り直したい

```bash
rm ~/nebuleuse/nebuleuse.db
neb ingest
```

`raw/` の md は無事なので何度でも再生成できる。

### `~/nebuleuse` 以外で動かしたい

```bash
export NEBULEUSE_HOME=/Volumes/USB/notes
neb stats
```

複数プロファイル（仕事用・個人用）を切り替える運用も可能。

---

## 7. 開発者向け

### テスト実行

```bash
uv run pytest -q
# 15 passed
```

埋め込みモデルはスタブに差し替え済みなので CI でも数秒で完走する。

### コード構成

```
src/nebuleuse/
├── cli.py        # neb サブコマンド（typer）
├── capture.py    # raw/ への保存
├── ingest.py     # raw/ → DB（差分検出込み）
├── chunker.py    # 見出し境界尊重チャンク分割
├── tokenize.py   # 日本語 bigram + ASCII トークナイズ
├── embed.py      # multilingual-e5
├── search.py     # vss + FTS5 (bigram) + RRF
├── ask.py        # search → LLM
├── llm.py        # mlx_lm.server クライアント
├── watch.py      # raw/ 監視 + debounced auto-ingest
└── db.py         # SQLite 接続・スキーマ
```

### 別言語から DB を読む

`nebuleuse.db` は普通の SQLite なので Swift / Rust / Go から直接開ける。
ベクター検索を使うなら sqlite-vss を読み込む必要があるが、`documents` / `chunks` テーブルだけ
なら標準 SQLite クライアントで読める。

```python
import sqlite3
conn = sqlite3.connect("/Users/you/nebuleuse/nebuleuse.db")
for row in conn.execute("SELECT path, title FROM documents"):
    print(row)
```
