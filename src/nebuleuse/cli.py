"""neb コマンドのエントリポイント。"""
from __future__ import annotations

import json
from typing import Optional

import typer

from . import ask as ask_mod
from . import capture as capture_mod
from . import ingest as ingest_mod
from . import llm as llm_mod
from . import search as search_mod

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Nébuleuse CLI")


@app.command()
def capture(
    file: Optional[str] = typer.Argument(None, help="path to a file; omit to read stdin"),
    source: Optional[str] = typer.Option(None, "--source", help="e.g. human, dialogue:claude"),
    title: Optional[str] = typer.Option(None, "--title"),
    no_ingest: bool = typer.Option(False, "--no-ingest", help="skip auto ingest after capture"),
):
    """stdin もしくはファイルから raw/ に保存する。"""
    text = capture_mod.read_input(file)
    path = capture_mod.capture(text, source=source, title=title)
    typer.echo(f"saved: {path}")
    if not no_ingest:
        stats = ingest_mod.ingest_all()
        typer.echo(f"ingested: {json.dumps(stats, ensure_ascii=False)}")


@app.command()
def ingest():
    """raw/ をスキャンして DB を更新する。"""
    stats = ingest_mod.ingest_all()
    typer.echo(json.dumps(stats, ensure_ascii=False, indent=2))


@app.command()
def search(
    query: str = typer.Argument(...),
    n: int = typer.Option(10, "-n", "--top", help="max hits"),
    full: bool = typer.Option(False, "--full", help="show full chunk content"),
):
    """ハイブリッド検索。"""
    hits = search_mod.search(query, top_n=n)
    if not hits:
        typer.echo("(no hits)")
        raise typer.Exit(0)
    for i, h in enumerate(hits, 1):
        title = h.title or h.document_path
        typer.echo(f"\n[{i}] score={h.score:.4f}  {title}")
        typer.echo(f"    src: {h.document_path}#{h.chunk_index}" + (f"  ({h.source})" if h.source else ""))
        snippet = h.content if full else h.content[:200].replace("\n", " ")
        typer.echo(f"    {snippet}{'' if full or len(h.content) <= 200 else ' ...'}")


@app.command()
def ask(
    question: str = typer.Argument(...),
    n: int = typer.Option(6, "-n", "--top", help="context chunks"),
    no_stream: bool = typer.Option(False, "--no-stream", help="disable streaming"),
):
    """検索 → LLM 回答。"""
    if not llm_mod.health():
        typer.echo(
            f"LLM server unreachable at {llm_mod.DEFAULT_BASE_URL}. "
            "Start it with `neb serve` (in another shell).",
            err=True,
        )
        raise typer.Exit(2)

    if no_stream:
        ans = ask_mod.ask(question, top_n=n)
        typer.echo(ans.text)
        _print_citations(ans.citations)
        return

    stream, hits = ask_mod.ask_stream(question, top_n=n)
    for delta in stream:
        typer.echo(delta, nl=False)
    typer.echo("")
    _print_citations(hits)


def _print_citations(hits):
    if not hits:
        return
    typer.echo("\n--- 出典 ---")
    for i, h in enumerate(hits, 1):
        typer.echo(
            f"[#{i}] {h.title or h.document_path}  "
            f"{h.document_path}#{h.chunk_index}"
            + (f"  ({h.source})" if h.source else "")
        )


@app.command()
def stats():
    """文書数・チャンク数・DB サイズを表示。"""
    typer.echo(json.dumps(search_mod.stats(), ensure_ascii=False, indent=2))


@app.command()
def serve(
    port: int = typer.Option(8080, "--port"),
    host: str = typer.Option("127.0.0.1", "--host"),
    model: str = typer.Option(llm_mod.DEFAULT_MODEL, "--model"),
):
    """mlx_lm.server を前面で起動する（薄いラッパー）。"""
    import os
    import sys

    args = [
        sys.executable,
        "-m",
        "mlx_lm.server",
        "--model",
        model,
        "--host",
        host,
        "--port",
        str(port),
    ]
    typer.echo(f"$ {' '.join(args)}")
    os.execvp(args[0], args)


if __name__ == "__main__":
    app()
