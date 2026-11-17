"""Access control for a hosted version: invite codes, signed session cookies, request limits.

Why it exists: every search calls a paid embedding service and every cited answer calls a paid
language model. Without a gate, anyone who finds the address could spend the owner's credit.

How it works:
- The owner creates one invite code per person (`priorart codes create`). Only a hash of the code
  is stored, so a leaked database does not leak the codes.
- Signing in with a code gives a cookie signed with SESSION_SECRET. The cookie holds no secret
  and cannot be forged or edited.
- Every search or answer is logged. A code may make `limit_per_hour` requests per rolling hour,
  and all codes together may make `daily_cap` requests per rolling day. Revoking a code stops it
  at once, even if its cookie is still valid.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

CODE_PREFIX = "spf-"
SESSION_SECONDS = 7 * 24 * 3600

SCHEMA = """
CREATE TABLE IF NOT EXISTS access_codes (
    id serial PRIMARY KEY,
    label text NOT NULL,
    code_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS usage_log (
    id bigserial PRIMARY KEY,
    code_id integer NOT NULL REFERENCES access_codes(id),
    kind text NOT NULL,
    at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS usage_log_code_at ON usage_log (code_id, at);
CREATE INDEX IF NOT EXISTS usage_log_at ON usage_log (at);
"""


def new_code() -> str:
    """A fresh invite code, about 120 bits of randomness."""
    return CODE_PREFIX + secrets.token_urlsafe(15)


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_session(code_id: int, secret: str, now: float | None = None) -> str:
    """A cookie value: 'code_id.expiry.signature'."""
    expiry = int((time.time() if now is None else now) + SESSION_SECONDS)
    payload = f"{code_id}.{expiry}"
    return f"{payload}.{_sign(payload, secret)}"


def read_session(token: str | None, secret: str, now: float | None = None) -> int | None:
    """Return the code id if the cookie is genuine and not expired, otherwise None."""
    if not token or not secret:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    code_id, expiry, signature = parts
    if not hmac.compare_digest(signature, _sign(f"{code_id}.{expiry}", secret)):
        return None
    try:
        if int(expiry) < (time.time() if now is None else now):
            return None
        return int(code_id)
    except ValueError:
        return None


@dataclass(frozen=True)
class Quota:
    allowed: bool
    used: int  # requests by this code in the last hour, including this one if allowed
    limit: int
    retry_after: int = 0  # seconds until a slot frees up, when not allowed
    reason: str = ""  # "hourly" or "daily" when not allowed

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


class AccessControl:
    def __init__(self, database_url: str, limit_per_hour: int, daily_cap: int):
        self.database_url = database_url
        self.limit = limit_per_hour
        self.daily_cap = daily_cap
        self._conn = None

    def _connection(self):
        import psycopg

        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.database_url, autocommit=True, prepare_threshold=None)
            self._conn.execute(SCHEMA)
        return self._conn

    def _run(self, sql: str, params: tuple = ()):
        """Run a query, reconnecting once if the connection went away (serverless databases)."""
        import psycopg

        for attempt in (1, 2):
            try:
                return self._connection().execute(sql, params)
            except (psycopg.OperationalError, psycopg.InterfaceError):
                self._conn = None
                if attempt == 2:
                    raise

    # administration

    def create_code(self, label: str) -> tuple[int, str]:
        code = new_code()
        row = self._run(
            "INSERT INTO access_codes (label, code_hash) VALUES (%s, %s) RETURNING id",
            (label, hash_code(code)),
        ).fetchone()
        return row[0], code

    def list_codes(self) -> list[tuple]:
        return self._run(
            "SELECT c.id, c.label, c.created_at, c.revoked,"
            " count(u.id) FILTER (WHERE u.at > now() - interval '24 hours'),"
            " count(u.id) "
            "FROM access_codes c LEFT JOIN usage_log u ON u.code_id = c.id "
            "GROUP BY c.id ORDER BY c.id"
        ).fetchall()

    def revoke(self, code_id: int) -> bool:
        cur = self._run("UPDATE access_codes SET revoked = true WHERE id = %s", (code_id,))
        return cur.rowcount > 0

    # sign in and limits

    def login(self, code: str) -> int | None:
        row = self._run(
            "SELECT id FROM access_codes WHERE code_hash = %s AND NOT revoked",
            (hash_code(code),),
        ).fetchone()
        return row[0] if row else None

    def is_active(self, code_id: int) -> bool:
        row = self._run(
            "SELECT 1 FROM access_codes WHERE id = %s AND NOT revoked", (code_id,)
        ).fetchone()
        return row is not None

    def usage(self, code_id: int) -> Quota:
        """Current use in the last hour, without counting a new request."""
        used = self._run(
            "SELECT count(*) FROM usage_log WHERE code_id = %s AND at > now() - interval '1 hour'",
            (code_id,),
        ).fetchone()[0]
        return Quota(used < self.limit, used, self.limit)

    def check_and_record(self, code_id: int, kind: str) -> Quota:
        """Count this request against the limits and log it, unless a limit is reached."""
        hour_used, oldest_wait, day_used = self._run(
            "SELECT count(*) FILTER (WHERE code_id = %s AND at > now() - interval '1 hour'),"
            " extract(epoch FROM (min(at) FILTER (WHERE code_id = %s"
            "   AND at > now() - interval '1 hour') + interval '1 hour' - now())),"
            " count(*) "
            "FROM usage_log WHERE at > now() - interval '24 hours'",
            (code_id, code_id),
        ).fetchone()
        if day_used >= self.daily_cap:
            return Quota(False, hour_used, self.limit, 3600, "daily")
        if hour_used >= self.limit:
            wait = int(oldest_wait or 60) + 1
            return Quota(False, hour_used, self.limit, wait, "hourly")
        self._run("INSERT INTO usage_log (code_id, kind) VALUES (%s, %s)", (code_id, kind))
        return Quota(True, hour_used + 1, self.limit)

    def refund(self, code_id: int) -> None:
        """Remove the latest logged request of a code (used when our service failed)."""
        self._run(
            "DELETE FROM usage_log WHERE id = (SELECT max(id) FROM usage_log WHERE code_id = %s)",
            (code_id,),
        )
