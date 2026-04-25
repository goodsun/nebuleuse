"""neb コマンドのエントリポイント。"""
from __future__ import annotations

import json
from typing import Optional

import typer

from . import capture as capture_mod
from . import ingest as ingest_mod
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
def stats():
    """文書数・チャンク数・DB サイズを表示。"""
    typer.echo(json.dumps(search_mod.stats(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
