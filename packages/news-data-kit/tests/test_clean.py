"""Tests for text cleaning."""

from news_data_kit.clean import strip_html, truncate, is_advertorial, clean_item


def test_strip_html_basic():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_cdata():
    assert strip_html("<![CDATA[Some text]]>") == "Some text"


def test_strip_html_empty():
    assert strip_html("") == ""
    assert strip_html(None) == ""


def test_truncate_short():
    assert truncate("Short text", 500) == "Short text"


def test_truncate_at_sentence():
    text = "First sentence。Second sentence。Third sentence that is quite long and should be cut."
    result = truncate(text, 40)
    assert result.endswith("。")
    assert len(result) <= 41


def test_truncate_no_sentence_boundary():
    text = "A" * 600
    result = truncate(text, 500)
    assert result.endswith("…")
    assert len(result) == 501


def test_is_advertorial_positive():
    assert is_advertorial("某某基金申购费率优惠公告")
    assert is_advertorial("", "本基金由XX管理人发行")


def test_is_advertorial_negative():
    assert not is_advertorial("美联储加息25个基点")
    assert not is_advertorial("腾讯Q3财报超预期")


def test_clean_item():
    title, summary, ft = clean_item("<b>Title</b>", "<p>Summary text</p>", "<div>Full</div>")
    assert title == "Title"
    assert summary == "Summary text"
    assert ft == "Full"
