"""
Contract tests for preseason games (gameType 1).

Two layers:
- a fixed past preseason date and game, checked all year round, so we know the
  wrapper handles preseason payloads at all;
- `live_preseason` tests, which only run while a preseason is under way and look
  at what the API is serving right now. This is where the NHL's own experiments
  show up: split-squad games, unfamiliar teams, missing fields.
"""

import pytest

from conftest import check_keys
from nhl_api_redux.games import Game
from nhl_api_redux.scores import fetch_scores, tailored_scores
from nhl_api_redux.standings import fetch_standings
from nhl_api_redux.status import game_is_scheduled
from nhl_api_redux.teams import fetch_season_schedule, get_all_team_abbrevs
from test_live_api import LANDING_KEYS, SCORE_GAME_KEYS

PRESEASON = 1
PAST_PRESEASON_DATE = "2025-09-21"
PAST_PRESEASON_GAME_ID = 2025010007


def test_past_preseason_scores_shape():
    games = fetch_scores(PAST_PRESEASON_DATE)["data"]["games"]
    assert games, f"no games on {PAST_PRESEASON_DATE}"
    for game in games:
        assert game["gameType"] == PRESEASON
        check_keys(game, *SCORE_GAME_KEYS, where=f"preseason score game {game.get('id')}")
    assert len(tailored_scores(PAST_PRESEASON_DATE)["data"]) == len(games)


def test_past_preseason_game_init():
    game = Game(gameid=PAST_PRESEASON_GAME_ID, delay=0)
    assert game.init_game(), "Game.init_game() did not complete for a preseason game"
    assert game.away_team_abbrev and game.home_team_abbrev


# --- current preseason ---------------------------------------------------------

def _todays_preseason_games():
    raw = fetch_scores()
    assert raw, "fetch_scores() for today returned nothing"
    return [g for g in raw["data"]["games"] if g.get("gameType") == PRESEASON]


@pytest.mark.live_preseason
def test_todays_preseason_games_shape():
    games = _todays_preseason_games()
    if not games:
        pytest.skip("no preseason games today")
    for game in games:
        # Games not yet started have no score, shots, goals or period.
        keys = SCORE_GAME_KEYS
        if game_is_scheduled(game.get("gameState")):
            keys = tuple(k for k in keys
                         if not k.endswith((".score", ".sog")) and k not in ("goals", "periodDescriptor"))
        check_keys(game, *keys, where=f"preseason score game {game.get('id')}")
    tailored_scores()


@pytest.mark.live_preseason
def test_todays_preseason_teams_are_known():
    games = _todays_preseason_games()
    if not games:
        pytest.skip("no preseason games today")
    known = set(get_all_team_abbrevs())
    unknown = {
        (game["id"], side, game[side].get("abbrev"), game[side].get("id"))
        for game in games
        for side in ("awayTeam", "homeTeam")
        if game[side].get("abbrev") not in known
    }
    assert not unknown, f"preseason games against teams the wrapper does not know: {sorted(unknown)}"


@pytest.mark.live_preseason
def test_todays_preseason_games_init():
    games = _todays_preseason_games()
    if not games:
        pytest.skip("no preseason games today")
    failed = []
    for scored in games:
        game = Game(gameid=scored["id"], delay=0)
        try:
            if not game.init_game():
                failed.append((scored["id"], "init_game() returned False"))
        except Exception as e:
            failed.append((scored["id"], repr(e)))
    assert not failed, f"preseason games that Game cannot load: {failed}"


@pytest.mark.live_preseason
def test_club_schedule_includes_preseason(season_state):
    games = fetch_season_schedule("MTL")
    preseason = [g for g in games if g.get("gameType") == PRESEASON]
    assert preseason, "club schedule has no preseason games during the preseason"
    for game in preseason:
        check_keys(game, "id", "gameDate", "gameState", "gameScheduleState",
                   where=f"schedule preseason game {game.get('id')}")
        assert str(game["id"]).startswith(str(season_state["season_id"])[:4]), (
            f"preseason game {game['id']} does not belong to season {season_state['season_id']}"
        )


@pytest.mark.live_preseason
def test_standings_during_preseason(season_state):
    raw = fetch_standings()["data"]
    if not raw:
        pytest.skip("standings/now is empty during the preseason")
    seasons = {team["seasonId"] for team in raw}
    current = season_state["season_id"]
    previous = current - 10001
    assert seasons <= {current, previous}, (
        f"standings/now serves seasons {sorted(seasons)}, expected {current} or {previous}"
    )
    assert {team["gameTypeId"] for team in raw} <= {2}, "standings/now serves non-regular-season standings"
