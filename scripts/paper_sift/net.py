"""Small HTTP layer: JSON payloads, retries with exponential backoff, and an injectable transport.

A transport is any callable `transport(method, url, headers, body, timeout) -> (status, body_bytes)`;
tests pass fakes, production uses urllib.
"""
import http.client
import json
import re
import ssl
import time
import urllib.error
import urllib.request

from . import USER_AGENT

RETRY_STATUSES = {429, 500, 502, 503, 504, 529}
# Bodies of the HttpError(0, ...) raised here: our own words, never a key or a server reply.
INVALID_REQUEST = b"invalid request (header or URL)"
CERT_FAILED = b"certificate verification failed (python.org builds: run Install Certificates.command)"
INVALID_JSON = b"invalid JSON response"
_SURROGATE = re.compile("[\ud800-\udfff]")


class HttpError(Exception):
    def __init__(self, status, body=b"", url=""):
        self.status, self.body, self.url = status, body, url
        super().__init__(f"HTTP {status} from {url}: {body[:300]!r}")


class AuthError(HttpError):
    """401 or 403: the key is missing, wrong or revoked."""


def is_client_error(e):
    """A 4xx other than 429, auth errors included: the request itself is wrong, so it is not retried and
    every other call would get the same answer."""
    return 400 <= e.status < 500 and e.status != 429


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
        failure = None
        try:
            status, data = transport(method, url, hdrs, body, timeout)
        except (OSError, ValueError, http.client.HTTPException) as e:
            if _certificate_error(e):  # permanent until certificates are installed: retrying cannot help
                failure = CERT_FAILED
            elif isinstance(e, ValueError):  # an invalid header value or URL; its message can quote a key
                failure = INVALID_REQUEST
            else:  # URLError, timeouts, refused connections, truncated or malformed responses
                status, data = None, repr(e).encode()
        if failure:  # raised here, outside the handler, so the original error is not chained
            raise HttpError(0, failure, url)
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


def _certificate_error(e):
    return (isinstance(e, ssl.SSLCertVerificationError)
            or isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError))


def _replace_surrogates(obj):
    """JSON may carry lone surrogates ("\\ud800"), which UTF-8 cannot encode: they become U+FFFD in every
    string, keys included."""
    if isinstance(obj, str):
        return _SURROGATE.sub("\ufffd", obj)
    if isinstance(obj, list):
        return [_replace_surrogates(x) for x in obj]
    if isinstance(obj, dict):
        return {_replace_surrogates(k): _replace_surrogates(v) for k, v in obj.items()}
    return obj


def request_json(method, url, **kwargs):
    """The parsed JSON reply. HttpError(0, "invalid JSON response") when it does not parse."""
    data = request(method, url, **kwargs)
    try:
        return _replace_surrogates(json.loads(data))
    except ValueError:  # not JSON, or not UTF-8
        pass
    raise HttpError(0, INVALID_JSON, url)  # outside the handler: the decoder error holds the whole reply
