"""日本語向け bigram 前処理（FTS5 補強）。

unicode61 トークナイザは CJK の分かち書きが弱く、「牧口」「siegeNgin」のような
固有名詞・造語を取りこぼす。本モジュールは：

- ASCII 単語はそのまま 1 トークン
- CJK / かな / カナの連なりは 2-gram に分解して空白区切り

の混合表現を返す。FTS5 にはこの bigram 化したテキストを格納し、
クエリも同じ関数を通すことで部分一致を実現する。
"""
from __future__ import annotations

import re

# CJK 統合漢字 + ひらがな + カタカナ + 全角英数の連続
_CJK_RUN = re.compile(
    r"[぀-ゟ゠-ヿ一-鿿ｦ-ﾟ㐀-䶿]+"
)
# ASCII 英数 + アンダースコア + ハイフンの連続
_ASCII_RUN = re.compile(r"[A-Za-z0-9_\-]+")


def _bigrams(s: str) -> list[str]:
    if len(s) <= 1:
        return [s]
    return [s[i : i + 2] for i in range(len(s) - 1)]


def to_index_text(text: str) -> str:
    """FTS5 に格納する空白区切りトークン列を返す。"""
    if not text:
        return ""
    out: list[str] = []
    cursor = 0
    n = len(text)
    while cursor < n:
        m_cjk = _CJK_RUN.match(text, cursor)
        if m_cjk:
            out.extend(_bigrams(m_cjk.group(0)))
            cursor = m_cjk.end()
            continue
        m_ascii = _ASCII_RUN.match(text, cursor)
        if m_ascii:
            tok = m_ascii.group(0).lower()
            if tok:
                out.append(tok)
            cursor = m_ascii.end()
            continue
        cursor += 1  # 記号・空白は捨てる
    return " ".join(out)


def to_query(text: str) -> str:
    """検索クエリを FTS5 MATCH 構文に変換する。

    全 bigram / ASCII トークンの AND 検索とする（OR より絞り込みが効く）。
    """
    tokens = to_index_text(text).split()
    if not tokens:
        return ""
    # FTS5 は引用符でリテラル扱い、AND（暗黙）で結合
    return " ".join(f'"{t}"' for t in tokens)
