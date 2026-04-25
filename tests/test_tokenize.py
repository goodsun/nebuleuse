from nebuleuse.tokenize import to_index_text, to_query


def test_ascii_lowercased_as_single_token():
    assert to_index_text("Hello-World").split() == ["hello-world"]


def test_japanese_bigram():
    out = to_index_text("牧口").split()
    assert out == ["牧口"]
    out = to_index_text("創価学会").split()
    assert out == ["創価", "価学", "学会"]


def test_mixed_text():
    out = to_index_text("siegeNgin の 設計").split()
    assert "siegengin" in out
    assert "設計" in out


def test_query_quotes_each_token():
    q = to_query("創価学会")
    assert q == '"創価" "価学" "学会"'


def test_empty():
    assert to_index_text("") == ""
    assert to_query("???") == ""
