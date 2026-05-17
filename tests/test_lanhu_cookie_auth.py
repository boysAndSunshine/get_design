"""Tests for Lanhu cookie capture validation."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lanhu_cookie_auth import (
    compare_cookie_headers,
    cookies_to_header,
    is_valid_lanhu_cookie,
    merge_cookie_headers,
)


def test_reject_incomplete_playwright_cookie():
    bad = (
        "session=eyJfZnJlc2giOmZhbHNlfQ.short; "
        "user_token=undefined; "
        "aliyungf_tc=abc; acw_tc=def; SERVERID=xyz"
    )
    assert is_valid_lanhu_cookie(bad) is False


def test_accept_complete_cookie_shape():
    good = (
        "PASSPORT=" + ("A" * 80) + "; "
        "user_token=" + ("eyJ" + "x" * 80) + "; "
        "session=.eJ" + ("y" * 200) + "; "
        "aliyungf_tc=abc; acw_tc=def; SERVERID=xyz"
    )
    assert is_valid_lanhu_cookie(good) is True


def test_merge_prefers_longer_session_and_valid_user_token():
    existing = (
        "PASSPORT=OLD_PASSPORT_VALUE; "
        "user_token=eyJvalid_existing_token_value_1234567890; "
        "session=.eJ" + ("a" * 200)
    )
    candidate = (
        "PASSPORT=P; user_token=undefined; session=short; aliyungf_tc=new"
    )
    merged = merge_cookie_headers(existing, candidate)
    parsed = dict(item.split("=", 1) for item in merged.split("; "))
    assert parsed["user_token"].startswith("eyJ")
    assert len(parsed["session"]) > 100
    assert parsed["PASSPORT"] == "OLD_PASSPORT_VALUE"


def test_cookies_to_header_skips_undefined_and_prefers_longer_value():
    header = cookies_to_header([
        {"name": "user_token", "value": "undefined", "domain": ".lanhuapp.com"},
        {"name": "user_token", "value": "eyJreal", "domain": ".lanhuapp.com"},
        {"name": "session", "value": "short", "domain": "lanhuapp.com"},
        {"name": "session", "value": ".eJ" + "x" * 150, "domain": ".lanhuapp.com"},
    ])
    parsed = dict(part.split("=", 1) for part in header.split("; "))
    assert parsed["user_token"] == "eyJreal"
    assert len(parsed["session"]) > 100
