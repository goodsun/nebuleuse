# Nébuleuse

Self-hosted knowledge base with SQLite-based vector + full-text search, driven by a local LLM.

> 散らばった思考が星雲を成し、その中から必要な星を見つける。
> 個人のための、完全にローカルで動くナレッジプール。

## 思想

Obsidian 的な「第二の脳」アプローチに対するアンチテーゼとして設計されています。
ノートを綺麗に整える作業そのものが思考の代替になることを避け、書き捨てたテキストを機械が潜在空間で繋ぐ。
人間は書くことだけに集中し、構造化は機械が担う。

**満たすべき要件**

- 書くコストが限りなく低い（分類・タグ・リンクは不要）
- 検索で確実に引ける（ベクター + 全文のハイブリッド）
- 取り出しやすい場所で動く（摩擦ゼロ、完全ローカル）
- 所有感がある（ファイル1つで持ち運べる）

## アーキテクチャ

```
┌─────────────────────────────────────────────┐
│  ~/nebuleuse/                               │
│  ├── raw/                  原本（プレーンテキスト）│
│  │   └── YYYY/MM/DD-slug.md                 │
│  ├── nebuleuse.db          SQLite (vss + FTS5)│
│  └── bin/                                   │
│      ├── neb-ingest        raw/ → db        │
│      ├── neb-search        ハイブリッド検索    │
│      └── neb-ask           検索 → LLM 回答   │
└─────────────────────────────────────────────┘
```

**原本とインデックスの分離：** `raw/` 配下のテキストファイルが正本。SQLite は導出物として扱い、壊れたら再生成可能。
将来別のシステムへ移行するときも、原本テキストがあれば困らない。

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

## ステータス

設計フェーズ。実装はこれから。

詳細な設計議事録：[docs/2026-04-24-design-dialogue.md](docs/2026-04-24-design-dialogue.md)

## ライセンス

MIT License — see [LICENSE](LICENSE).
