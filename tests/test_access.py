"""Invite codes, signed cookies and request limits."""

import os

import pytest

from priorart import access
from priorart.access import (
    AccessControl,
    hash_code,
    make_session,
    new_code,
    read_session,
)

SECRET = "x" * 40


def test_codes_are_random_and_hashed():
    a, b = new_code(), new_code()
    assert a != b and a.startswith("spf-") and len(a) > 20
    assert hash_code(a) == hash_code(f"  {a}\n")  # pasted with spaces still works
    assert hash_code(a) != a


def test_session_round_trip():
    token = make_session(7, SECRET, now=1000)
    assert read_session(token, SECRET, now=1001) == 7


def test_session_rejects_tampering_wrong_secret_and_expiry():
    token = make_session(7, SECRET, now=1000)
    code_id, expiry, signature = token.split(".")
    assert read_session(f"8.{expiry}.{signature}", SECRET, now=1001) is None
    assert read_session(f"{code_id}.{int(expiry) + 99999}.{signature}", SECRET, now=1001) is None
    assert read_session(token, "y" * 40, now=1001) is None
    assert read_session(token, SECRET, now=1000 + access.SESSION_SECONDS + 5) is None
    assert read_session("garbage", SECRET) is None
    assert read_session(None, SECRET) is None
    assert read_session(token, "", now=1001) is None


psycopg = pytest.importorskip("psycopg")

ADMIN_URL = os.environ.get(
    "TEST_ADMIN_URL", "postgresql://priorart:priorart@localhost:5432/priorart"
)
TEST_DB = "priorart_access_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/" + TEST_DB


@pytest.fixture()
def ac():
    try:
        admin = psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("no PostgreSQL available")
    admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
    admin.execute(f"CREATE DATABASE {TEST_DB}")
    yield AccessControl(TEST_URL, limit_per_hour=3, daily_cap=5)
    admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")


def test_login_and_revoke(ac):
    code_id, code = ac.create_code("alice")
    assert ac.login(code) == code_id
    assert ac.login("spf-not-a-real-code") is None
    assert ac.is_active(code_id)
    assert ac.revoke(code_id)
    assert ac.login(code) is None
    assert not ac.is_active(code_id)


def test_hourly_limit_counts_each_request_and_then_blocks(ac):
    code_id, _ = ac.create_code("alice")
    left = [ac.check_and_record(code_id, "search").remaining for _ in range(3)]
    assert left == [2, 1, 0]
    blocked = ac.check_and_record(code_id, "search")
    assert not blocked.allowed and blocked.reason == "voyage"
    assert 0 < blocked.retry_after <= 3601
    assert ac.usage(code_id).used == 3  # the refused request was not logged


def test_limit_is_per_code(ac):
    a, _ = ac.create_code("a")
    b, _ = ac.create_code("b")
    for _ in range(3):
        ac.check_and_record(a, "search")
    assert not ac.check_and_record(a, "search").allowed
    assert ac.check_and_record(b, "search").allowed


def test_daily_cap_applies_to_all_codes_together(ac):
    ids = [ac.create_code(str(i))[0] for i in range(3)]
    results = [ac.check_and_record(ids[i % 3], "search") for i in range(6)]
    assert [r.allowed for r in results] == [True] * 5 + [False]
    assert results[-1].reason == "daily"


def test_answers_have_their_own_hourly_limit(ac):
    answers_ac = AccessControl(TEST_URL, limit_per_hour=5, daily_cap=50, answer_limit=2)
    code_id, _ = answers_ac.create_code("alice")
    assert answers_ac.check_and_record(code_id, "answer").allowed
    assert answers_ac.check_and_record(code_id, "answer").allowed
    third = answers_ac.check_and_record(code_id, "answer")
    assert not third.allowed and third.reason == "anthropic"
    assert answers_ac.check_and_record(code_id, "search").allowed  # searches still go through


def test_every_request_counts_against_the_embedding_limit(ac):
    answers_ac = AccessControl(TEST_URL, limit_per_hour=3, daily_cap=50, answer_limit=3)
    code_id, _ = answers_ac.create_code("alice")
    for kind in ("search", "answer", "search"):
        assert answers_ac.check_and_record(code_id, kind).allowed
    blocked = answers_ac.check_and_record(code_id, "answer")
    assert not blocked.allowed and blocked.reason == "voyage"


def test_answers_have_a_daily_cap_of_their_own(ac):
    capped = AccessControl(TEST_URL, 10, 50, answer_limit=10, answer_daily_cap=2)
    ids = [capped.create_code(str(i))[0] for i in range(3)]
    assert capped.check_and_record(ids[0], "answer").allowed
    assert capped.check_and_record(ids[1], "answer").allowed
    third = capped.check_and_record(ids[2], "answer")
    assert not third.allowed and third.reason == "anthropic_daily"
    assert capped.check_and_record(ids[2], "search").allowed
