# Nébuleuse

Self-hosted knowledge base with SQLite-based vector + full-text search, driven by a local LLM.

> 散らばった思考が星雲を成し、その中から必要な星を見つける。
> 個人のための、完全にローカルで動くナレッジプール。

## 思想

Nébuleuse は **「把握可能な外部記憶」** を目指す個人ナレッジプールです。

LLM サービス（Claude Projects・メモリ機能など）が提供する「自動化された外部記憶」の便利さの裏側には、
**ユーザーが何が読まれているか・何が消えたか・なぜその話題が引き出されたかを把握できない** という問題があります。
記憶の境界線がサービス側に握られ、思考の軌跡は要約として返ってきて、当時の生の言葉が残らない。

Nébuleuse の対立軸はそこにあります：

- **生のテキストが手元に残る** —— `raw/` の md ファイルが正本。書いた通りに残る
- **検索プロセスが透明** —— 何がヒットしたかが全部見える
- **インデックスは使い捨て可能** —— 原本こそが真実、いつでも再生成できる
- **忘却も自分で制御** —— 消したければ `rm` するだけ、本当に消える
- **完全ローカル** —— サーバーに送らない、サービスが終わっても動く

Obsidian 的な「第二の脳」アプローチ（ノートを綺麗に整える作業が思考の代替になる）とも、
Claude 的な「自動化された記憶」（便利だが把握できない）とも違う、第三の道を取ります。

**満たすべき要件**

- 書くコストが限りなく低い（分類・タグ・リンクは不要）
- 検索で確実に引ける（ベクター + 全文のハイブリッド）
- 取り出しやすい場所で動く（摩擦ゼロ、完全ローカル）
- 何が起きているかが透明（自動だが、把握可能）

## 補完関係

Claude が提供するのは「便利な外部知能」、Nébuleuse が提供するのは「把握可能な外部記憶」。別物として両立します。
実際、`raw/` に入る MD の多くは AI との壁打ちを経て結晶化したテキストになることを想定しています。
**対話を Claude に任せ、結晶を自分で持つ** —— これが現実的な使い方になるでしょう。

## アーキテクチャ

```
┌─────────────────────────────────────────────┐
│  ~/nebuleuse/                               │
│  ├── raw/                  原本（md ファイル）  │
│  │   └── YYYY/MM/DD-slug.md                 │
│  ├── nebuleuse.db          SQLite (vss + FTS5)│
│  └── .ingest_state.json    取り込み状態       │
└─────────────────────────────────────────────┘
```

**原本とインデックスの分離：** `raw/` 配下のテキストファイルが正本。SQLite は導出物として扱い、壊れたら再生成可能。
別システムへ移行するときも、原本テキストがあれば困らない。

## 技術選定

| レイヤー | 採用 |
|---|---|
| ストレージ | SQLite（[sqlite-vss](https://github.com/asg017/sqlite-vss) + FTS5） |
| 埋め込み | multilingual-e5 系（MLX、Apple Silicon ネイティブ） |
| LLM | [Bonsai-8B](https://huggingface.co/prism-ml/Bonsai-8B-mlx-1bit)（1-bit、MLX、1.15GB） |
| 検索戦略 | ベクター + 全文の RRF (Reciprocal Rank Fusion) ハイブリッド |

LLM は差し替え可能な前提で設計。Bonsai-8B / Bonsai-4B / Gemma / Qwen など MLX で動く軽量モデルを想定。
重いタスクはクラウド LLM（例：RunPod 上の llm-jp-4）にエスカレーション可能。

## なぜ SQLite 一本か

- ファイル1個で完結する所有感（バックアップは `cp` するだけ）
- ベクター検索（sqlite-vss）と全文検索（FTS5）が同じ DB の同じテーブルで完結し、1クエリで RRF 統合できる
- 「ベクター vs 全文」と「RAG vs エージェンティック」は人間と機械の役割分担という同じ構造を持ち、SQLite は2軸 × 2軸のすべてのセルに自然に対応できる
- どこにでもある SQLite なので、Python / Swift / Rust など別言語の別プロセスから同じファイルを読める

## CLI

```
neb capture        # stdin / clipboard / file から raw/ に保存（対話 MD の取り込み）
neb ingest         # raw/ をスキャンして DB を更新
neb search "..."   # ハイブリッド検索結果を表示
neb ask "..."      # 検索 → LLM 回答
neb stats          # 文書数・チャンク数・DB サイズ
neb serve          # mlx_lm.server を起動
```

## ステータス

設計フェーズ。実装はこれから。

**設計ドキュメント:**
- [docs/design.md](docs/design.md) —— 全体設計書
- [docs/2026-04-24-design-dialogue.md](docs/2026-04-24-design-dialogue.md) —— 技術選定の議事録
- [docs/2026-04-24-why-nebuleuse.md](docs/2026-04-24-why-nebuleuse.md) —— なぜ作るかの議事録

## ライセンス

MIT License — see [LICENSE](LICENSE).
