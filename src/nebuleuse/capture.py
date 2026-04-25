"""raw/ への書き込みプリミティブ。"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import yaml

from . import db


def _slugify(s: str, max_len: int = 50) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-぀-ヿ一-鿿]", "", s)
    s = s.strip("-") or "note"
    return s[:max_len]


def _infer_title(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s:
            return s[:60]
    return "untitled"


def capture(text: str, *, source: str | None = None, title: str | None = None) -> Path:
    if not text.strip():
        raise ValueError("empty input")

    title = title or _infer_title(text)
    now = dt.datetime.now()
    raw_root = db.data_dir() / "raw"
    target_dir = raw_root / f"{now.year:04d}" / f"{now.month:02d}"
    target_dir.mkdir(parents=True, exist_ok=True)

    base = f"{now.day:02d}-{_slugify(title)}"
    path = target_dir / f"{base}.md"
    seq = 1
    while path.exists():
        seq += 1
        path = target_dir / f"{base}-{seq}.md"

    fm = {"title": title, "created_at": now.astimezone().isoformat()}
    if source:
        fm["source"] = source
    fm_text = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n"

    path.write_text(fm_text + text.rstrip() + "\n", encoding="utf-8")
    return path


def read_input(file: str | None) -> str:
    if file:
        return Path(file).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        raise SystemExit("no input: pass a file or pipe text via stdin")
    return sys.stdin.read()
