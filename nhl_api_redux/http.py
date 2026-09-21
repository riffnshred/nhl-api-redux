"""
The single outbound HTTP seam for this package, and the pacing that hangs off it.

Every endpoint module used to call `requests.get` directly. That works, but it means a
fresh TCP connection and TLS handshake for each one - twelve call sites, no reuse - and
a consumer polling `api-web.nhle.com` on a few-second interval pays that handshake for
nearly every request it makes. Routing everything through one `Session` keeps the
connections alive between calls.

It also gives the package one place that sees all of its own traffic, which is what
anything cross-cutting needs in order to exist at all. Three things live here:

1. **A freshness cache.** The NHL's CDN stamps each response with how long it stays
   fresh, so a request made inside that window can only get back the bytes we already
   hold. Serving those locally costs no round trip and no staleness - the first request
   after the window expires still goes out.
2. **Priority-aware pacing.** A minimum spacing between requests and a token bucket
   capping the sustained rate. Tiers reserve a fraction of the bucket from the tiers
   below, so background work cannot starve whatever the caller has marked as important.
3. **429 handling.** A 429 opens a cooldown honouring `Retry-After`; requests below the
   top tier are refused outright for its duration rather than sent into a block that is
   still in force.

**None of it is on by default.** A library that paces or caches without being asked is
a library that surprises people, so an unconfigured package behaves exactly as it did
before any of this existed: `_get` calls the session and returns. Consumers opt in with
`configure()`.

Nothing here patches anything global, and none of the state is process-wide by
construction - it hangs off `NHLSession`, of which the module keeps one convenient
default instance.

Typical use:

    import nhl_api_redux

    nhl_api_redux.configure(min_spacing=0.25, rate=1.0, burst=20, cooldown=60)

    with nhl_api_redux.priority(nhl_api_redux.HIGH):
        game.update()
"""

import contextlib
import contextvars
import re
import threading
import time
from collections import deque

import requests
from requests.adapters import HTTPAdapter

from .domains import DEFAULT_TIMEOUT
from .logger import logger

# Priority tiers, ordered most to least protected. HIGH draws on neither the bucket nor
# the spacing queue and is never refused; NORMAL and LOW are paced, and LOW has to leave
# more of the bucket behind than NORMAL does, so under pressure it yields first.
HIGH = "high"
NORMAL = "normal"
LOW = "low"

# Fraction of the bucket each tier must leave behind for the tiers above it.
DEFAULT_RESERVE = {NORMAL: 0.25, LOW: 0.5}

# How long a request of each tier waits for its turn before failing fast. A poll that
# waits longer than its own interval is queueing data that will be stale on arrival; a
# job that runs hourly can afford to wait out a bucket refill.
DEFAULT_PATIENCE = {NORMAL: 5.0, LOW: 60.0}

# One more than the largest thread pool we expect to be called from, so a burst of
# concurrent jobs reuses pooled connections instead of discarding them and reopening.
_POOL_SIZE = 20

_MAX_AGE_RE = re.compile(r"max-age=(\d+)")

# The tier the current call belongs to. A contextvar rather than a parameter because the
# alternative is threading `priority=` through every call site in this package and every
# method that reaches one - `Game.update()` included - to carry something none of them
# have any business knowing about. Contextvars are per-thread and per-task, so a caller
# that sets this around a block scopes it to that block and nothing else.
_priority = contextvars.ContextVar("nhl_api_redux_priority", default=NORMAL)


@contextlib.contextmanager
def priority(tier):
    """
    Run a block's NHL requests at `tier`.

    Args:
        tier: HIGH, NORMAL or LOW

    Example:
        with priority(HIGH):
            game.update()
    """
    token = _priority.set(tier)
    try:
        yield
    finally:
        _priority.reset(token)


class RateLimited(requests.exceptions.RequestException):
    """
    Raised instead of sending a request the pacer will not allow.

    Subclasses RequestException so this package's own `except RequestException` handlers
    treat it as a failed fetch, which is what it is - just one that cost no request and
    no round trip. Callers that distinguish the two can ask `is_paused()`.
    """


class _Pacer:
    """
    Cache, token bucket and cooldown state for one session.

    Created only by `NHLSession.configure()`; an unconfigured session has none and does
    no pacing at all.
    """

    def __init__(self, min_spacing=0.25, rate=1.0, burst=20, cooldown=60.0,
                 max_cooldown=600.0, probe_interval=0.0, cache=True,
                 reserve=None, patience=None):
        self.min_spacing = min_spacing
        self.rate = rate
        self.burst = burst
        self.cooldown = cooldown
        self.max_cooldown = max_cooldown
        self.probe_interval = probe_interval
        self.cache = cache
        self.reserve = dict(DEFAULT_RESERVE if reserve is None else reserve)
        self.patience = dict(DEFAULT_PATIENCE if patience is None else patience)

        self._lock = threading.Lock()

        # monotonic() deadlines: next free slot, when the current 429 cooldown ends, and
        # when a HIGH request may next probe it
        self._next_slot = 0.0
        self._blocked_until = 0.0
        self._next_probe = 0.0

        self._tokens = float(burst)
        self._refilled_at = time.monotonic()

        # Send times from the last minute, for measuring the rate a 429 arrived at
        self._recent = deque()

        # url -> (expiry, status, headers, content, encoding, reason)
        self._responses = {}

        self.sent = 0
        self.delayed = 0
        self.skipped = 0
        self.cached = 0
        self.rate_limits = 0

    # -- freshness cache ---------------------------------------------------------

    def get_cached(self, url):
        """
        Return a stored response while the CDN copy it came from is still fresh.

        The origin cannot have anything newer inside that window, so this is not a
        staleness tradeoff - the next request after it expires still goes out, and a
        poll faster than the window simply stops costing anything.

        Returns:
            A requests.Response rebuilt from the stored copy, or None
        """
        if not self.cache:
            return None

        with self._lock:
            entry = self._responses.get(url)
            if not entry or entry[0] <= time.monotonic():
                return None
            self.cached += 1

        return self._rebuild(url, entry)

    def store(self, url, response):
        """Keep a response for as long as the CDN says its copy stays fresh."""
        if not self.cache or response.status_code != 200:
            return

        ttl = self._freshness(response)
        if ttl <= 0:
            return

        with self._lock:
            now = time.monotonic()
            self._responses[url] = (
                now + ttl,
                response.status_code,
                dict(response.headers),
                response.content,
                response.encoding,
                response.reason,
            )
            # Entries are only ever seconds old, so a sweep of the expired ones is enough
            # to keep this bounded without tracking sizes or ordering
            if len(self._responses) > 64:
                self._responses = {u: e for u, e in self._responses.items()
                                   if e[0] > now}

    def _freshness(self, response):
        """
        Seconds this response stays fresh: its max-age less the age it arrived with.

        Subtracting Age matters - a response handed over 10 seconds into a 19 second
        window has 9 left, and caching it for the full 19 would hold a stale scoreboard
        through the window in which the CDN got a new one.
        """
        cache_control = response.headers.get("Cache-Control", "")
        if "no-store" in cache_control or "no-cache" in cache_control:
            return 0

        match = _MAX_AGE_RE.search(cache_control)
        if not match:
            return 0

        try:
            age = int(response.headers.get("Age", 0))
        except (TypeError, ValueError):
            age = 0

        return max(0, int(match.group(1)) - age)

    def _rebuild(self, url, entry):
        """Build a fresh Response from a stored copy, so callers never share one."""
        _, status, headers, content, encoding, reason = entry

        response = requests.Response()
        response.status_code = status
        response.headers = requests.structures.CaseInsensitiveDict(headers)
        response._content = content
        response._content_consumed = True
        response.encoding = encoding
        response.reason = reason
        response.url = url

        return response

    # -- admission ---------------------------------------------------------------

    def reserve_slot(self, url, tier):
        """
        Claim the next send slot, or refuse the request.

        Returns:
            Seconds the caller must wait before sending

        Raises:
            RateLimited: During a 429 cooldown, or when the wait exceeds the tier's
                         patience
        """
        with self._lock:
            now = time.monotonic()
            self._refill(now)

            if now < self._blocked_until:
                return self._probe_or_refuse(tier, url, now)

            if tier == HIGH:
                # Exempt, and deliberately so. Any queue or budget the top tier shares
                # with the rest is a queue the rest can starve it out of, which is the
                # one outcome this whole mechanism exists to prevent.
                self._commit(now)
                return 0.0

            wait = self._wait_for_turn(tier, now)

            if wait > self.patience.get(tier, DEFAULT_PATIENCE[LOW]):
                # The queue is longer than the request is worth. Failing now frees the
                # thread and lets the caller's own backoff decide when to try again.
                self.skipped += 1
                raise RateLimited(
                    f"NHL API throttled - {url} ({tier}) would wait {wait:.1f}s"
                )

            self._commit(now + wait)
            if wait > 0:
                self.delayed += 1

            return wait

    def _probe_or_refuse(self, tier, url, now):
        """
        During a cooldown, let the top tier through and refuse everything else.

        This is the half-open state of a circuit breaker. Silencing the lower tiers is
        what gives the API room; the HIGH requests that carry on are also how the
        cooldown finds out the API is answering again. A 429 on one of them simply
        extends the cooldown, so a caller cannot talk itself back into trouble.
        """
        remaining = self._blocked_until - now

        if tier != HIGH:
            self.skipped += 1
            raise RateLimited(
                f"NHL API rate limited - not sending {url} for another {remaining:.0f}s"
            )

        if self.probe_interval and now < self._next_probe:
            self.skipped += 1
            raise RateLimited(
                f"NHL API rate limited - next {HIGH} priority request in "
                f"{self._next_probe - now:.0f}s ({remaining:.0f}s left on the cooldown)"
            )

        self._next_probe = now + self.probe_interval
        self._commit(now)
        logger.debug("%s priority request allowed through the cooldown - %.0fs left",
                     HIGH, remaining)

        return 0.0

    def _wait_for_turn(self, tier, now):
        """
        Seconds until a paced request may go out.

        Two constraints: the spacing queue, which stops simultaneous callers from
        bursting, and the token bucket, which caps the sustained rate. A tier waits for
        the bucket to climb back above its floor rather than spending into the headroom
        the tier above it may need.
        """
        slot = max(now, self._next_slot)
        floor = self.reserve.get(tier, 0.0) * self.burst
        token_wait = max(0.0, (floor + 1 - self._tokens) / self.rate) if self.rate else 0.0

        return max(slot - now, token_wait)

    def _commit(self, send_at):
        """Record a reservation handed out for `send_at`. Caller holds the lock."""
        self._tokens = max(0.0, self._tokens - 1)
        self._next_slot = max(self._next_slot, send_at + self.min_spacing)
        self.sent += 1
        self._recent.append(send_at)

    def _rate_last_minute(self, now):
        """
        Requests sent in the last 60 seconds. Caller holds the lock.

        This is the number worth having when a 429 arrives: the NHL publishes no limit,
        so the rate we were sending at the moment one landed is the only measurement of
        where the line actually is.
        """
        while self._recent and self._recent[0] < now - 60:
            self._recent.popleft()

        return len(self._recent)

    def _refill(self, now):
        """Top the bucket up for the time that has passed. Caller holds the lock."""
        self._tokens = min(self.burst, self._tokens + (now - self._refilled_at) * self.rate)
        self._refilled_at = now

    # -- rate limit handling -----------------------------------------------------

    def note_response(self, response):
        """
        Open a cooldown when the API says it has had enough, and close it when it stops.

        Only the top tier reaches the API during a cooldown, so its responses are the
        only evidence available about whether the block is still on. A 429 extends the
        pause; anything else ends it, because the thing the pause was waiting for has
        happened and there is no reason to stay silent for the remainder of a guess.
        """
        if response.status_code != 429:
            self._note_success()
            return

        delay = self._retry_after(response)

        # The NHL publishes no rate limit, so the only way to learn one is from the
        # responses themselves. Everything the 429 carried goes in the log: what it asked
        # for, and which Cloudflare edge said so.
        asked_for = response.headers.get("Retry-After") or "nothing"
        ray = response.headers.get("CF-Ray", "?")

        with self._lock:
            self.rate_limits += 1
            now = time.monotonic()
            measured = self._rate_last_minute(now)
            deadline = now + delay
            # Consecutive 429s must not shorten a cooldown already in progress
            if deadline > self._blocked_until:
                self._blocked_until = deadline
                self._next_probe = now + self.probe_interval
                logger.warning(
                    "NHL API returned 429 after %d requests in the last minute "
                    "(Retry-After: %s, CF-Ray: %s) - pausing NHL requests for %ds "
                    "(%s priority keeps going%s)",
                    measured, asked_for, ray, delay, HIGH,
                    f", at most every {self.probe_interval:.0f}s" if self.probe_interval
                    else ""
                )

    def _note_success(self):
        """End a cooldown early once a request gets through."""
        with self._lock:
            if not self.is_paused():
                return

            self._blocked_until = 0.0
            self._next_probe = 0.0
            # The bucket refilled to full while things were quiet, so letting everything
            # resume at once would put a burst through the moment the block lifts - which
            # is how it started. Resume from a quarter tank instead.
            self._tokens = min(self._tokens, self.burst * 0.25)
            logger.info("NHL API answering again - resuming normal requests")

    def _retry_after(self, response):
        """Read Retry-After if the response carries a usable one, else use the default."""
        header = response.headers.get("Retry-After", "")
        try:
            delay = float(header)
        except (TypeError, ValueError):
            # Retry-After may also be an HTTP date. Parsing it is not worth it here - the
            # default cooldown is the right order of magnitude either way.
            return self.cooldown

        return max(self.cooldown, min(delay, self.max_cooldown))

    def is_paused(self):
        """Whether a 429 cooldown is in force right now."""
        return time.monotonic() < self._blocked_until

    def stats(self):
        """A snapshot of what the pacer has done, for a caller's health reporting."""
        with self._lock:
            now = time.monotonic()
            paused_for = max(0.0, self._blocked_until - now)
            return {
                "rate_last_minute": self._rate_last_minute(now),
                "sent": self.sent,
                "delayed": self.delayed,
                "skipped": self.skipped,
                "cached": self.cached,
                "rate_limits": self.rate_limits,
                "paused_seconds": round(paused_for, 1),
            }


class NHLSession:
    """
    A pooled `requests.Session` for the NHL API, optionally paced.

    Unconfigured, `get()` is a thin wrapper over the session and nothing else happens.
    `configure()` attaches a `_Pacer` and turns on the cache, the bucket and the
    cooldown.
    """

    def __init__(self):
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=_POOL_SIZE)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._pacer = None

    def configure(self, min_spacing=0.25, rate=1.0, burst=20, cooldown=60.0,
                  max_cooldown=600.0, probe_interval=0.0, cache=True,
                  reserve=None, patience=None):
        """
        Turn on caching and pacing for this session, or re-tune what is already on.

        Args:
            min_spacing: Minimum seconds between two requests
            rate: Sustained ceiling in requests per second, for the paced tiers
            burst: Bucket size - how many requests may go out back to back
            cooldown: Seconds to stop sending after a 429 with no usable Retry-After
            max_cooldown: Ceiling for a Retry-After the API asks for, so a stray header
                          cannot park a caller for hours
            probe_interval: Minimum seconds between HIGH priority requests during a
                            cooldown. 0 leaves them ungated, which is the default - the
                            freshness cache is usually the only pacing they need. A
                            large value approximates going dark until the cooldown ends.
            cache: Serve a response again while the CDN copy it came from is still fresh
            reserve: {tier: fraction} of the bucket each tier leaves for the tiers above
                     it. Defaults to DEFAULT_RESERVE. This is policy - a caller that
                     knows what its own jobs are worth should say so.
            patience: {tier: seconds} each tier waits for a slot before failing fast.
                      Defaults to DEFAULT_PATIENCE.

        Returns:
            The active _Pacer
        """
        if self._pacer is None:
            self._pacer = _Pacer(min_spacing, rate, burst, cooldown, max_cooldown,
                                 probe_interval, cache, reserve, patience)
            logger.info("NHL request pacing enabled - %.2fs apart, %.2g/s sustained, "
                        "%ds pause after a 429", min_spacing, rate, cooldown)
            return self._pacer

        pacer = self._pacer
        pacer.min_spacing = min_spacing
        pacer.rate = rate
        pacer.burst = burst
        pacer.cooldown = cooldown
        pacer.max_cooldown = max_cooldown
        pacer.probe_interval = probe_interval
        pacer.cache = cache
        if reserve is not None:
            pacer.reserve = dict(reserve)
        if patience is not None:
            pacer.patience = dict(patience)
        return pacer

    def get(self, url, **kwargs):
        """
        GET `url`, paced and cached if this session has been configured for it.

        Applies DEFAULT_TIMEOUT unless the caller passes its own. Returns the
        `requests.Response` untouched - status checking, JSON decoding and error
        handling stay with the call site, which is where the differences between
        endpoints live.

        Raises:
            RateLimited: When pacing is on and the request will not be sent
        """
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)

        pacer = self._pacer
        if pacer is None:
            return self._session.get(url, **kwargs)

        # A full url including the query string, so two calls to the same path with
        # different params are not confused for one another
        key = requests.Request("GET", url, params=kwargs.get("params")).prepare().url

        # Checked before a slot is claimed: a response the CDN would not have replaced
        # yet should cost nothing at all
        cached = pacer.get_cached(key)
        if cached is not None:
            return cached

        wait = pacer.reserve_slot(key, _priority.get())
        if wait > 0:
            time.sleep(wait)

        response = self._session.get(url, **kwargs)
        pacer.note_response(response)
        pacer.store(key, response)

        return response

    def is_paused(self):
        """Whether requests are being held back by a 429 cooldown right now."""
        return self._pacer.is_paused() if self._pacer else False

    def stats(self):
        """Pacer counters, or None when this session was never configured."""
        return self._pacer.stats() if self._pacer else None


# The default session every endpoint module in this package uses. Callers that want a
# second one with its own pacing can build their own NHLSession, but there is only ever
# one NHL API, so one is normally the right number.
SESSION = NHLSession()


def configure(min_spacing=0.25, rate=1.0, burst=20, cooldown=60.0, max_cooldown=600.0,
              probe_interval=0.0, cache=True, reserve=None, patience=None):
    """
    Turn on caching and pacing for the default session, or re-tune what is already on.

    The parameters are spelled out rather than forwarded as **kwargs so that `help()`
    and `inspect.signature()` show them. See `NHLSession.configure` for what each does.
    """
    return SESSION.configure(min_spacing=min_spacing, rate=rate, burst=burst,
                             cooldown=cooldown, max_cooldown=max_cooldown,
                             probe_interval=probe_interval, cache=cache,
                             reserve=reserve, patience=patience)


def is_paused():
    """
    Whether NHL requests are being held back by a 429 cooldown right now.

    Callers use this to tell a fetch that failed because the API is not answering from
    one this module refused to send. They are not the same thing and must not be handled
    the same way: the second is already being paced here, so a caller that also backs
    off on it backs off twice.
    """
    return SESSION.is_paused()


def stats():
    """Pacer counters for the default session, or None when it was never configured."""
    return SESSION.stats()


def _get(url, **kwargs):
    """GET `url` on the default session. The seam every endpoint module goes through."""
    return SESSION.get(url, **kwargs)
