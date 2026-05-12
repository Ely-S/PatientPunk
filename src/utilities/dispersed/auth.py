"""HMAC-SHA256 request signing for the Dispersed REST API.

Per https://otoyinc.mintlify.app/service-consumers/service-consumers-authenticate-requests,
every request must include four headers:

  X-API-Key   : the public key (pk_...)
  X-Time      : Unix timestamp in MILLISECONDS
  X-Nonce     : 16 random bytes hex-encoded (32 chars)
  X-Signature : HMAC-SHA256 of a 7-part pipe-delimited canonical string,
                signed with the secret key (sk_...)

Canonical string:
  publicKey | timestamp | nonce | METHOD | pathname | queryString | bodySha256

Important per the docs:
  - timestamp is milliseconds, with ±5min server tolerance
  - nonce is 32 hex chars (16 random bytes); tracked for 24h, no reuse
  - query string keys AND values must be sorted alphabetically before signing
  - JSON bodies should be canonicalized with sorted keys, no whitespace
  - empty body SHA-256 is the well-known
    e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode

EMPTY_BODY_SHA256 = hashlib.sha256(b"").hexdigest()


def _canonical_query(query: dict | str | None) -> str:
    """Return query string with keys+values sorted alphabetically.

    Dispersed signs the alphabetically-sorted form, so we must sign the same
    shape we put on the wire. If callers pass a pre-built string we still
    re-parse and re-sort to guarantee match.
    """
    if not query:
        return ""
    if isinstance(query, str):
        # Reparse `a=1&b=2` form into a list of (k,v) pairs.
        pairs = [p.split("=", 1) if "=" in p else (p, "") for p in query.split("&") if p]
    else:
        pairs = list(query.items())
    pairs.sort(key=lambda kv: (kv[0], str(kv[1])))
    return urlencode(pairs)


def make_headers(
    public_key: str,
    secret_key: str,
    method: str,
    path: str,
    query: dict | str | None = None,
    body: bytes = b"",
    *,
    _timestamp_ms: int | None = None,
    _nonce: str | None = None,
) -> dict[str, str]:
    """Return the four signed headers Dispersed expects.

    `_timestamp_ms` and `_nonce` are for tests only — production always
    generates fresh values per request.
    """
    if not public_key or not secret_key:
        raise ValueError("public_key and secret_key are required")

    ts = str(_timestamp_ms if _timestamp_ms is not None else int(time.time() * 1000))
    nonce = _nonce if _nonce is not None else secrets.token_hex(16)
    query_str = _canonical_query(query)
    body_sha = hashlib.sha256(body).hexdigest() if body else EMPTY_BODY_SHA256

    canonical = "|".join((
        public_key,
        ts,
        nonce,
        method.upper(),
        path,
        query_str,
        body_sha,
    ))
    sig = hmac.new(
        secret_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "X-API-Key": public_key,
        "X-Time": ts,
        "X-Nonce": nonce,
        "X-Signature": sig,
    }
