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
nhl-api-redux = { git = "https://github.com/riffnshred/nhl-api-redux.git", tag = "v0.2.0" }
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
from nhl_api_redux.scores import fetch_scores, tailored_scores, fetch_empty_scores

fetch_scores(date=None, max_retries=3, retry_delay=1, debug_data=None)
tailored_scores(date=None, debug_data=None)
fetch_empty_scores()   # a valid, gameless payload — useful in the offseason
```

`tailored_scores()` returns `{"timestamp", "currentDate", "data": [...]}` where each
game carries `id`, `season`, `gameType`, `gameState`, `gameScheduleState`,
`startTimeUTC`, `clock`, `period`, `periodDescriptor`, `goals`, and an `awayTeam` /
`homeTeam` pair with `id`, `abbrev`, `name`, `sog`, `score` and `record`. Playoff
games also carry `seriesStatus`.

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
    Team,
)

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

## Credits

Endpoint discovery owes a lot to
[Zmalski/NHL-API-Reference](https://github.com/Zmalski/NHL-API-Reference).

This project is not affiliated with or endorsed by the National Hockey League.

## License

MIT — see [LICENSE](LICENSE).
