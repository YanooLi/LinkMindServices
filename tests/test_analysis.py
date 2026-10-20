import pytest

from app.analysis import classifier, fetcher, heuristics


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/YanooLi/LinkMindServices", "safe"),
    ("https://www.cmu.edu/", "safe"),
    ("http://192.168.0.1/admin", "suspicious"),
    ("https://user@evil.example.com", "suspicious"),
    ("https://xn--pple-43d.com/login", "suspicious"),
    ("https://apple-id-verify.top/signin", "suspicious"),
])
def test_risk_rules(url, expected):
    score, _ = heuristics.score_signals(heuristics.url_signals(url))
    assert ("safe" if score >= 0.5 else "suspicious") == expected


def test_keyword_categories():
    assert classifier.keyword_category("https://www.youtube.com/watch?v=x", None) == "video"
    assert classifier.keyword_category("https://example.com", "Breaking news today") == "news"
    assert classifier.keyword_category("https://example.com", None) == "other"


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/", "http://localhost/", "http://169.254.169.254/latest",
                                 "file:///etc/passwd", "ftp://example.com"])
async def test_fetcher_blocks_private_targets(url):
    with pytest.raises(fetcher.UnsafeURL):
        await fetcher.assert_public(url)
