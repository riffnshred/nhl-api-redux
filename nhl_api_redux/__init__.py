"""
A Python wrapper for the NHL's api-web and stats REST endpoints.

Endpoint functions live in the submodules (`games`, `scores`, `standings`, `teams`,
`seasons`, `rosters`, `leaders`, `server`). What is re-exported here is the HTTP
behaviour shared by all of them - see `nhl_api_redux.http`.

Caching and pacing are off unless asked for:

    import nhl_api_redux

    nhl_api_redux.configure(min_spacing=0.25, rate=1.0, burst=20, cooldown=60)

    with nhl_api_redux.priority(nhl_api_redux.HIGH):
        game.update()
"""

from .http import (
    DEFAULT_PATIENCE,
    DEFAULT_RESERVE,
    HIGH,
    LOW,
    NORMAL,
    NHLSession,
    RateLimited,
    configure,
    is_paused,
    priority,
    stats,
)

__all__ = [
    "HIGH",
    "NORMAL",
    "LOW",
    "DEFAULT_RESERVE",
    "DEFAULT_PATIENCE",
    "NHLSession",
    "RateLimited",
    "configure",
    "is_paused",
    "priority",
    "stats",
]
