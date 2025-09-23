import pytest

from llmseo.utils import normalize_url


@pytest.mark.parametrize(
    "input_url,expected",
    [
        ("https://example.com/path?foo=1", "https://example.com/path?foo=1"),
        ("example.com/path?foo=1", "https://example.com/path?foo=1"),
        ("https://example.com?foo=1", "https://example.com/?foo=1"),
        ("https://example.com/path?foo=1#frag", "https://example.com/path?foo=1#frag"),
    ],
)
def test_normalize_url_preserves_important_parts(input_url, expected):
    assert normalize_url(input_url) == expected


def test_normalize_url_rejects_empty_values():
    with pytest.raises(ValueError):
        normalize_url("   ")
