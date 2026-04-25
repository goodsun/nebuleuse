# Nébuleuse TODO / バックログ

設計の穴・未着手の改善項目を、実装前の生の議論ごと残しておく場所。
完了した項目は `design.md` の Phase チェックリストへ移動する。

---

## 1. 「書くコストゼロ」の達成度を上げる（高優先）

### 指摘

> `raw/` が正本、SQLite は導出物——この設計思想は正しい。でも `neb capture` で
> 「stdin / file から取り込む」って、書く側にどれだけ摩擦があるか。「書くコストが
> 限りなく低い」という要件と、CLI で取り込む動作の間に乖離がある。メモした瞬間に
> ingest される体験になっているかどうかが肝。`neb watch` で自動 ingest は解決して
> いるか——でもそれは raw/ に書く摩擦がゼロかとは別の話。

（2026-04-25 のレビューより）

### 認識

- `neb watch` は「書き込みが起きたら ingest される」を保証するだけ。
  **書く行為そのものの摩擦**には触っていない。
- 「書くコストの低さ」は単一指標ではなく、入力モダリティごとに別の課題：

| モダリティ | 現状の摩擦 | 状態 |
|---|---|---|
| AI 対話の結晶化 (`pbpaste \| neb capture`) | 低い | OK |
| 思いついた一行 | エディタ起動 + ファイル名 + 保存が必要 | **要対応** |
| 長文の自筆 | エディタ直書き + `neb watch` | OK（元々書く側の摩擦が高い領域） |
| 音声・出先 | 未対応 | Phase 4 |

### 打ち手（小さい順）

- [ ] **`neb jot "..."` を追加** — 引数の文字列をそのまま `raw/` に保存。
      `echo ... \| neb capture` の糖衣だが心理的摩擦は段違い。
      タイトルは先頭 50 字から自動生成、source は `human` 既定。
- [ ] **`neb capture` のエディタモード** — 引数なしで起動したら `$EDITOR` を開き、
      書いて保存したら自動 ingest。設計書 §7.1 に既述だが未実装。
- [ ] **シェル関数 / Raycast 等のホットキー** — Cmd+Shift+N でテキスト入力 → 即 capture。
      ここまで来て初めて「書く瞬間に取り込まれる」体験になる。Nébuleuse 本体ではなく
      ユーザー環境側の整備として `usage.md` に手順を追記する形が妥当か。
- [ ] **iOS Shortcuts → Mac mini への HTTP POST**（Phase 4） — 出先からの一行を
      取り込む経路。簡単な HTTP エンドポイントを `neb serve` 系に同居させるか別プロセスか
      は要検討。

### 検討メモ

- `neb jot` と `neb capture` の責務分離はどこで切るか。
  - 案 A: `jot` は引数文字列専用、`capture` は stdin/file 専用（モード明確）
  - 案 B: `capture "..."` を許容して `jot` は別名（typer の alias）
  - 当面は **案 A** が「設計の最小性」と整合。

---

## 2. LLM 常駐化（中優先）

- [ ] launchd plist で `neb serve` を Mac 起動時に自動起動
- [ ] PID 管理・ログローテーション
- [ ] `neb serve --background` で簡易バックグラウンド起動を提供する案も

---

## 3. 検索品質の継続改善（中優先）

- [ ] チャンク戦略の見直し: 対話 MD（`source: dialogue:claude`）はターン境界で
      切るか、見出し境界のままで良いか実測
- [ ] 埋め込みモデルの差し替え検証（multilingual-e5-small で軽量化、性能差）
- [ ] 同義語・ゆれの取り扱い（「Nébuleuse」「ネビュルーズ」「nebuleuse」を等価扱い）

---

## 4. LLM 品質チューニング（中優先）

- [ ] Llama-3.2-3B では出典 `[#N]` の付与指示が守られない場面あり
- [ ] Qwen2.5-7B-4bit や gemma 系の比較
- [ ] プロンプト改善（few-shot 例を入れる、出力フォーマットを強制する）

---

## 5. その他（低優先）

- [ ] 検索結果のリランキング（cross-encoder で上位 N を再採点）
- [ ] Whisper ローカル取り込み（`neb capture --voice <audio>`）
- [ ] エージェンティックループ（LLM が再検索を判断する）
- [ ] Web UI（chat 形式、検索結果の可視化）

---

## 完了済み（参考）

design.md の Phase チェックリストを正とし、ここでは概要のみ：

- ✅ Phase 1：MVP（capture/ingest/search/stats、差分検出も）
- ✅ Phase 2：ローカル LLM 統合（serve/ask、出典表示）
- ✅ Phase 3：日本語 FTS bigram、`neb watch`、pytest 整備
- ✅ ドキュメント整備（README/design/usage）
