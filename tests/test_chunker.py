from nebuleuse.chunker import chunk_text


def test_empty_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_one_chunk():
    chunks = chunk_text("hello world")
    assert len(chunks) == 1
    assert chunks[0].content == "hello world"
    assert chunks[0].char_start == 0


def test_heading_boundary_split():
    text = "# A\nbody A\n\n# B\nbody B\n"
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0].content.startswith("# A")
    assert chunks[1].content.startswith("# B")


def test_long_section_chunked_with_overlap():
    long = "x" * 1500
    text = f"# H\n{long}"
    chunks = chunk_text(text, max_chars=500, overlap=50)
    assert len(chunks) >= 3
    # オーバーラップが効いているか（隣接チャンクの開始位置が前チャンクより手前）
    for prev, cur in zip(chunks, chunks[1:]):
        assert cur.char_start < prev.char_end
