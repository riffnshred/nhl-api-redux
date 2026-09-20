""" Known Domains """
BASE = "https://api.nhle.com"
BASEWEB = "https://api-web.nhle.com/v1"

# (connect, read) timeout in seconds for every outbound request. A healthy api-web
# answers well under a second; the read budget is deliberately generous because the
# NHL edge sometimes stalls for ~20s before answering. Callers on a tight poll
# interval should lower max_retries rather than raise this.
DEFAULT_TIMEOUT = (5, 20)

# Shorter (connect, read) budget for fallback requests. They only run after a
# primary fetch has already burned its own retries, inside a call the caller is
# still waiting on, so they get one quick attempt rather than a generous one.
FALLBACK_TIMEOUT = (3, 8)
