from pathlib import Path

from nebuleuse import capture, db


def test_capture_creates_file_with_frontmatter():
    path = capture.capture("# 議事録\n本文です", source="dialogue:claude")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "title: 議事録" in text
    assert "source: dialogue:claude" in text
    assert "本文です" in text


def test_capture_avoids_collision():
    p1 = capture.capture("# Same\nA")
    p2 = capture.capture("# Same\nB")
    assert p1 != p2
    assert p2.stem.endswith("-2")


def test_capture_under_data_dir():
    path = capture.capture("hello")
    raw_root = db.data_dir() / "raw"
    assert raw_root in path.parents
