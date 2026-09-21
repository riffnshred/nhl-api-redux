# nhl-api-redux

A Python wrapper for the NHL's public endpoints — the modern `api-web.nhle.com/v1`
service plus the older `api.nhle.com/stats` REST service.

The NHL does not document these endpoints, and their payloads are large and deeply
nested. This package covers the parts that matter for building a scoreboard or a
game tracker, and each area exposes two levels:

- `fetch_*` returns the raw API payload, wrapped with a UTC timestamp.
- `tailored_*` returns a flattened, stable shape with only the fields you are
  likely to want.

> Status: alpha. The public surface is still moving between minor versions.

## Installation

Requires Python 3.11+.

```bash
pip install git+https://github.com/riffnshred/nhl-api-redux.git
```

With [uv](https://docs.astral.sh/uv/), pin it to a tag in your `pyproject.toml`:

```toml
dependencies = ["nhl-api-redux"]

[tool.uv.sources]
nhl-api-redux = { git = "https://github.com/riffnshred/nhl-api-redux.git", tag = "v0.5.0" }
```

## Quick start

```python
from nhl_api_redux.scores import tailored_scores

scores = tailored_scores()          # today; or tailored_scores("2025-03-15")
for game in scores["data"]:
    away, home = game["awayTeam"], game["homeTeam"]
    print(f"{away['abbrev']} {away['score']} @ {home['abbrev']} {home['score']}"
          f" — {game['gameState']}")
```

## Modules

### `scores` — the day's slate

Wraps `/v1/score/{date}`, which carries every game for a date plus live score,
shots, clock and goal summaries.

```python
from nhl_api_redux.scores import (
    fetch_scores, fetch_scoreboard, tailored_scores, fetch_empty_scores,
)

fetch_scores(date=None, max_retries=3, retry_delay=1, debug_data=None, timeout=(5, 20))
fetch_scoreboard(date=None, max_retries=1, retry_delay=1, timeout=(3, 8))
tailored_scores(date=None, debug_data=None, max_retries=3, retry_delay=1,
                timeout=(5, 20), fallback=False, fallback_max_retries=1,
                fallback_timeout=(3, 8))
fetch_empty_scores()   # a valid, gameless payload — useful in the offseason
```

Both return **`None`** when every attempt failed. That is deliberately distinct from a
day with no games (which returns a payload with an empty `data` list): on a poll loop,
hold your last known value when you get `None` instead of publishing an empty
scoreboard over a good one. Every request carries a `(connect, read)` timeout, and
HTTP errors, timeouts and malformed bodies are all retried.

Callers on a tight poll interval should lower `max_retries` rather than raise the
timeout — at the defaults a total outage costs up to `3 x 20s + 2 x retry_delay`.

`tailored_scores()` returns `{"timestamp", "currentDate", "data": [...]}` where each
game carries `id`, `season`, `gameType`, `gameState`, `gameScheduleState`,
`startTimeUTC`, `clock`, `period`, `periodDescriptor`, `goals`, and an `awayTeam` /
`homeTeam` pair with `id`, `abbrev`, `name`, `sog`, `score` and `record`. Playoff
games also carry `seriesStatus`.

#### Falling back to the scoreboard

`/v1/score/{date}` has gone dark for a single date while the rest of the host stayed
healthy. `tailored_scores(fallback=True)` covers that: once `fetch_scores` has spent
its retries, it makes one short-timeout attempt at `/v1/scoreboard/{date}` — which
carries the same slate, live score, shots and clock — and maps it into the same game
shape.

```python
scores = tailored_scores(fallback=True)
if scores is None:
    ...                              # both endpoints failed; hold your last value
elif scores.get("source") == "scoreboard":
    ...                              # degraded, but usable
```

- The envelope gains `"source": "scoreboard"` when the fallback produced the data.
  A healthy `score/` reply has no `source` key at all.
- `score/` stays the primary. The fallback never pre-empts it, and `None` still
  means both endpoints failed, as distinct from a day with no games.
- The fallback's view is thinner: `goals` is always `[]`, playoff games carry no
  `seriesStatus` key, and finished games lose `sog` and `clock`. Games that are live
  or not yet started are identical field for field. The next healthy poll restores
  everything.
- `fetch_scoreboard()` is available on its own. Use the dated form rather than
  `scoreboard/now`, which resolves against the server's clock and disagrees with the
  caller around the midnight rollover; the day is then found by matching the date in
  `gamesByDate`, not by trusting the payload's `focusedDate`.

### `games` — tracking one live game

`Game` polls `/v1/gamecenter/{id}/landing` into a rolling buffer, so the state it
exposes can be held back to line up with a TV or radio broadcast.

```python
from nhl_api_redux.games import Game

game = Game(gameid=2024020500, delay=15)
game.init_game()

while True:
    game.update()
    print(game.away_team_abbrev, game.away_score, "-",
          game.home_score, game.home_team_abbrev,
          game.state, game.period_number, game.clock)
    time.sleep(10)
```

- `delay` is how many seconds the exposed state trails the API, to compensate for
  broadcast lag.
- `update(auto_sync=True)` fetches and applies state once the delay has elapsed.
  With `auto_sync=False` it instead returns the number of seconds until the new
  data is due, so you can hand that to your own scheduler and call `sync_state()`
  yourself.
- Initialising a game also pulls both teams' season stats and builds their
  `W-L-OTL` records into `away_team_record` / `home_team_record`.
  Before the season's first regular-season game (offseason, preseason) those come
  from the previous season; `team_stats_season_id` says which season was used.
- `Game(debug=True, debug_game_data_file="path/to/game.json")` replays a saved
  payload instead of calling the API.

### `standings`

```python
from nhl_api_redux.standings import (
    tailored_standings,
    sort_league_standings,
    sort_division_standings,
    sort_conference_standings,
    sort_wildcard_standings,
)
```

`tailored_standings()` flattens `/v1/standings/now` to one entry per team with
points, regulation/OT records, streak, goal differential and last-ten
(`l10Wins` / `l10Losses` / `l10OtLosses`). The `sort_*` helpers regroup that list;
`sort_wildcard_standings()` returns each conference with its divisions first (top
three each) and a `wildcard` list last, ordered by `wildcardSequence`.
`tailored_standings("2026-04-17")` returns the standings as of a date instead, which is
how you get a finished season's final table once `now` has moved on.

### `teams`

Static reference data plus per-team lookups.

```python
from nhl_api_redux.teams import (
    teams_info,        # id -> full name, location, triCode, franchise id
    teams_branding,    # triCode -> primary/accent/contrast colours
    teams_id,          # short name -> id
    get_all_team_abbrevs,
    fetch_season_schedule,
    find_previous_and_next_games,
    find_last_completed_game,
    Team,
)

fetch_season_schedule("MTL")             # the season the API considers current
fetch_season_schedule("MTL", 20252026)   # a specific season
find_last_completed_game(schedule)       # last game that is over, or None

team = Team("Canadiens")
team.abbrev            # "MTL"
team.previous_game, team.next_game
team.roster()
team.get_team_stats(season="20252026", game_type_id=2)
```

`get_all_team_abbrevs()` returns the 32 active teams. `teams_branding` is
deliberately wider: it also carries the special-event codes (`HGS`, `MAT`, `MCD`,
`MKN`) worn on alternate jerseys, which are not teams and have no roster. Retired
franchises live in `RETIRED_TEAM_ABBREVS` and are reachable with
`get_all_team_abbrevs(include_retired=True)`.

Includes the Utah Mammoth (id 68, `UTA`); the retired Arizona Coyotes entry is kept
in `teams_info` so historical games still resolve.

### `seasons`

```python
from nhl_api_redux.seasons import (
    get_current_season,          # 20252026
    get_previous_season_id,      # 20262027 -> 20252026
    get_current_season_details,
    get_season_state,
)

get_season_state()
# {"season_id", "season", "state", "days_until_season",
#  "preseason_start", "season_start", "regular_season_end", "season_end",
#  "number_of_games"}
```

The API publishes season boundary dates but never a phase, so `get_season_state()`
derives one — `offseason`, `preseason`, `regular` or `playoffs` — and counts down
the days until the season starts while that number is still meaningful.

### `rosters`

```python
from nhl_api_redux.rosters import fetch_team_roster, fetch_all_rosters

fetch_team_roster("MTL")
fetch_all_rosters(["MTL", "TOR", "BOS"])
```

### `leaders`

Top-ten leaders per category from the stats service.

```python
from nhl_api_redux.leaders import tailored_leaders

tailored_leaders("goals", "skaters")
tailored_leaders("points", "skaters", position="D")
tailored_leaders("assists", "skaters", rookie=True)
tailored_leaders("savePctg", "goalies")
```

### `status`

Game state codes and the predicates that read them, so you never compare raw
strings:

```python
from nhl_api_redux.status import (
    GAME_STATE_CODE, GAME_SCHEDULE_STATE_CODE, GAME_OUTCOME_CODE,
    game_is_scheduled, game_is_pre_game, game_is_live,
    game_is_critical, game_is_over, game_schedule_is_irregular,
)
```

`game_is_critical()` covers the NHL's `CRIT` state — a close game inside the final
minutes, when you want to poll faster.

## Requests, caching and rate limits

Every endpoint in the package goes out on one pooled `requests.Session`, so repeated
calls reuse the connection instead of paying a TLS handshake each time. That happens
whether you configure anything or not.

Caching and pacing are **off by default** — an unconfigured package sends exactly what
you ask it to, when you ask. Turn them on once, at startup:

```python
import nhl_api_redux

nhl_api_redux.configure(
    min_spacing=0.25,   # minimum seconds between any two requests
    rate=1.0,           # sustained ceiling in requests/second
    burst=20,           # how many may go out back to back
    cooldown=60,        # seconds to stop sending after a 429
    cache=True,         # reuse a response while the CDN copy is still fresh
)
```

The cache is plain HTTP freshness: the NHL's CDN stamps each response with a
`max-age`, and a repeat request inside that window is served from the copy already in
hand. It is not a staleness tradeoff — the origin has nothing newer to give until the
window expires. On a fast poll loop it removes most of your request volume for free.

### Priority

Not all of your requests matter equally. Mark the ones that do:

```python
from nhl_api_redux import priority, HIGH, LOW

with priority(HIGH):
    game.update()        # never paced, never refused, even during a cooldown

with priority(LOW):
    fetch_standings()    # first to yield when the bucket runs low
```

The default is `NORMAL`. `LOW` must leave more of the token bucket behind than
`NORMAL` does, so background work cannot starve a live poll; `HIGH` draws on neither
the bucket nor the spacing queue, because any budget it shares is a budget the rest
can starve it out of. The fractions are yours to set via `configure(reserve=...)` —
what your own jobs are worth is your policy, not the library's.

`priority()` is a context manager over a `contextvar`, so it scopes to the block and
is isolated per thread and per asyncio task. Nothing needs a `priority=` argument.

### When a request is not sent

A 429 opens a cooldown honouring `Retry-After`. For its duration, anything below
`HIGH` raises `RateLimited` instead of being sent:

```python
from nhl_api_redux import RateLimited, is_paused, stats

try:
    scores = tailored_scores()
except RateLimited:
    ...  # cost no round trip
```

`RateLimited` subclasses `requests.exceptions.RequestException`, so existing handlers
already catch it. If you back off on failures, use `is_paused()` to tell "the API is
failing" from "we declined to send" — the second is already being paced here, and
backing off on top of it backs off twice.

`stats()` returns a counter snapshot (`sent`, `cached`, `skipped`, `delayed`,
`rate_limits`, `rate_last_minute`, `paused_seconds`) suitable for a health payload, or
`None` if you never called `configure()`.

For a second session with its own settings, build an `NHLSession` directly. The
package's own endpoint functions always use the default one.

## Logging

The package logs to the `nhl_api_redux` logger and configures nothing itself, so by
default it is silent. Route it from your application:

```python
import logging
logging.getLogger("nhl_api_redux").addHandler(my_handler)
```

For standalone use, `NHL_API_LOG_LEVEL=DEBUG` sets the package's level directly.

## Example payloads

Captured responses ship with the package for offline development, and resolve
wherever it is installed:

```python
from nhl_api_redux.examples import load_exemple

load_exemple("scores_exemple.json")
load_exemple("standings_exemple.json")
load_exemple("game.json")
```

## Testing against the live API

The NHL changes these endpoints without notice, so the tests call the real API and
check the fields the wrapper depends on.

```bash
uv run pytest
```

Payload shapes are checked against a fixed past game, date and season, so the
suite passes in the offseason too. The run header and summary show the current
season phase. During the preseason, extra `live_preseason` tests look at the games
the API is serving that day, and the run is flagged, because the API is unstable
then. `NHL_API_FORCE_SEASON_STATE=preseason` runs the suite as if it were the
preseason.

CI runs the suite daily
([`.github/workflows/api-contract.yml`](.github/workflows/api-contract.yml)). A
failure opens an `api-contract` issue, labelled `preseason` when relevant, and
the next passing run closes it.

## Credits

Endpoint discovery owes a lot to
[Zmalski/NHL-API-Reference](https://github.com/Zmalski/NHL-API-Reference).

This project is not affiliated with or endorsed by the National Hockey League.

## License

MIT — see [LICENSE](LICENSE).
