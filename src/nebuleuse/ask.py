"""検索結果を文脈に LLM へ問う。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from . import llm, search

ASK_TOP_N = 6
MAX_CONTEXT_CHARS = 4000

SYSTEM_PROMPT = (
    "あなたはユーザー個人のナレッジプール (Nébuleuse) を参照して回答するアシスタントです。"
    "以下のルールを厳守してください:\n"
    "1. 提供されたコンテキストの範囲で回答する。コンテキストにない事は『ナレッジに記録なし』と明示する。\n"
    "2. 推測や一般論で埋めない。出典がある事実だけを述べる。\n"
    "3. 回答中で参照した事実には [#1] [#2] のように番号で出典を引用する。\n"
    "4. 簡潔に、ユーザーが書いた言葉を尊重した語彙で答える。"
)


@dataclass
class Answer:
    text: str
    citations: list[search.Hit]


def _build_context(hits: list[search.Hit]) -> str:
    blocks: list[str] = []
    used = 0
    for i, h in enumerate(hits, 1):
        header = f"[#{i}] {h.title or h.document_path} ({h.document_path}#{h.chunk_index})"
        body = h.content.strip()
        block = f"{header}\n{body}"
        if used + len(block) > MAX_CONTEXT_CHARS and blocks:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def _build_messages(question: str, hits: list[search.Hit]) -> list[dict]:
    context = _build_context(hits)
    user = (
        f"# コンテキスト\n{context}\n\n"
        f"# 質問\n{question}\n\n"
        "コンテキストを根拠に、出典番号 [#N] を付けて回答してください。"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


DEFAULT_MAX_TOKENS = 512


def ask(question: str, *, top_n: int = ASK_TOP_N, max_tokens: int = DEFAULT_MAX_TOKENS) -> Answer:
    hits = search.search(question, top_n=top_n)
    if not hits:
        return Answer(text="ナレッジに記録なし。", citations=[])
    text = llm.chat(_build_messages(question, hits), max_tokens=max_tokens)
    return Answer(text=text, citations=hits)


def ask_stream(
    question: str, *, top_n: int = ASK_TOP_N, max_tokens: int = DEFAULT_MAX_TOKENS
) -> tuple[Iterator[str], list[search.Hit]]:
    hits = search.search(question, top_n=top_n)
    if not hits:
        return iter(["ナレッジに記録なし。\n"]), []
    return llm.chat_stream(_build_messages(question, hits), max_tokens=max_tokens), hits
