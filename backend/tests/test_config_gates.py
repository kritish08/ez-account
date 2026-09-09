"""Startup configuration gates.

config.py already refuses to boot on a missing or weak JWT_SECRET and a
malformed MASTER_ENCRYPTION_KEY. CORS_ORIGINS deserves the same
treatment: silently degrading to a permissive default is how a
production deploy ends up more open than anyone intended.
"""

import pytest

from app.config import parse_cors_origins


def test_explicit_origin_list_is_parsed():
    assert parse_cors_origins("https://a.example,https://b.example") == [
        "https://a.example",
        "https://b.example",
    ]


def test_whitespace_and_empty_entries_are_ignored():
    assert parse_cors_origins(" https://a.example , , https://b.example ") == [
        "https://a.example",
        "https://b.example",
    ]


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_missing_cors_origins_is_refused(raw):
    """A missing value must fail loudly, not fall back to a wildcard.

    Regression: an unset CORS_ORIGINS silently started the app with
    allow_origins=["*"]. The accompanying comment argued that pairing
    the wildcard with allow_credentials=False made it safe, but this API
    authenticates with an Authorization header rather than cookies, so
    the credentials flag buys nothing here — the wildcard just let any
    origin read every unauthenticated endpoint.
    """
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        parse_cors_origins(raw)


def test_wildcard_is_refused():
    """`*` cannot be combined with credentialed requests per the CORS spec."""
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        parse_cors_origins("*")


def test_wildcard_mixed_into_a_list_is_refused():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        parse_cors_origins("https://a.example,*")
