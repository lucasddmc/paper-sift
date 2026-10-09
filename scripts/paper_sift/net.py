"""Small HTTP layer: JSON payloads, retries with exponential backoff, and an injectable transport.

A transport is any callable `transport(method, url, headers, body, timeout) -> (status, body_bytes)`;
tests pass fakes, production uses urllib.
"""
import http.client
import json
import time
import urllib.error
import urllib.request

from . import USER_AGENT

RETRY_STATUSES = {429, 500, 502, 503, 504, 529}


class HttpError(Exception):
    def __init__(self, status, body=b"", url=""):
        self.status, self.body, self.url = status, body, url
        super().__init__(f"HTTP {status} from {url}: {body[:300]!r}")


class AuthError(HttpError):
    """401 or 403: the key is missing, wrong or revoked."""


def urllib_transport(method, url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def request(method, url, *, headers=None, payload=None, transport=None, retries=8, sleep=time.sleep,
            timeout=90, max_wait=60.0):
    """Return the response body. Retries RETRY_STATUSES and network errors; raises AuthError or HttpError."""
    transport = transport or urllib_transport
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        hdrs["Content-Type"] = "application/json"
    wait = 2.0
    for attempt in range(retries + 1):
        try:
            status, data = transport(method, url, hdrs, body, timeout)
        except (OSError, http.client.HTTPException) as e:  # URLError, timeouts, refused connections, truncated or malformed responses
            status, data = None, repr(e).encode()
        if status is not None and 200 <= status < 300:
            return data
        if status in (401, 403):
            raise AuthError(status, data, url)
        if status is not None and status not in RETRY_STATUSES:
            raise HttpError(status, data, url)
        if attempt == retries:
            raise HttpError(status or 0, data, url)
        sleep(min(wait, max_wait))
        wait *= 2


def request_json(method, url, **kwargs):
    return json.loads(request(method, url, **kwargs))
