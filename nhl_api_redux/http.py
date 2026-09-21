"""
The single outbound HTTP seam for this package.

Every endpoint module used to call `requests.get` directly. That works, but it means a
fresh TCP connection and TLS handshake for each one - twelve call sites, no reuse - and
a consumer polling `api-web.nhle.com` on a few-second interval pays that handshake for
nearly every request it makes. Routing everything through one `Session` keeps the
connections alive between calls.

It also gives the package one place that sees all of its own traffic, which is what
anything cross-cutting (caching, pacing, rate limit handling) needs to exist at all.
"""

import requests
from requests.adapters import HTTPAdapter

from .domains import DEFAULT_TIMEOUT

# One more than the largest thread pool we expect to be called from, so a burst of
# concurrent jobs reuses pooled connections instead of discarding them and reopening.
_POOL_SIZE = 20


def _build_session():
    """A Session with a pool wide enough for a multi-threaded caller."""
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=_POOL_SIZE)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = _build_session()


def _get(url, **kwargs):
    """
    GET `url` on the shared session.

    Applies the package's DEFAULT_TIMEOUT unless the caller passes its own. Returns the
    `requests.Response` untouched - status checking, JSON decoding and error handling
    stay with the call site, which is where the differences between endpoints live.
    """
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return SESSION.get(url, **kwargs)
