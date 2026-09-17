"""
Contract tests for the regular season and playoff endpoints.

Payload shapes are checked against a fixed past game, date and season, so a test
never fails just because it is the offseason and there is nothing to play. The
"now" endpoints are only checked for responding with the expected envelope.
"""

import pytest

from conftest import check_keys
from nhl_api_redux.games import Game, fetch
from nhl_api_redux.leaders import fetch_leaders, tailored_leaders
from nhl_api_redux.rosters import fetch_team_roster
from nhl_api_redux.scores import fetch_scores, tailored_scores
from nhl_api_redux.seasons import tailored_seasons
from nhl_api_redux.server import ping_nhl_api
from nhl_api_redux.standings import (
    fetch_standings,
    sort_wildcard_standings,
    tailored_standings,
)
from nhl_api_redux.teams import Team, fetch_season_schedule, get_all_team_abbrevs

# A completed season with data that will not move.
PAST_SEASON = 20242025
REGULAR_SEASON_DATE = "2025-03-15"
PLAYOFF_DATE = "2025-05-01"
REGULAR_SEASON_GAME_ID = 2024020500

SCORE_GAME_KEYS = (
    "id", "season", "gameType", "startTimeUTC", "gameScheduleState", "gameState",
    "awayTeam.id", "awayTeam.abbrev", "awayTeam.name.default", "awayTeam.score", "awayTeam.sog",
    "homeTeam.id", "homeTeam.abbrev", "homeTeam.name.default", "homeTeam.score", "homeTeam.sog",
    "periodDescriptor", "goals",
)

LANDING_KEYS = (
    "gameDate", "startTimeUTC", "gameState", "gameScheduleState", "season",
    "awayTeam.id", "awayTeam.abbrev", "awayTeam.commonName.default", "awayTeam.placeName.default",
    "homeTeam.id", "homeTeam.abbrev", "homeTeam.commonName.default", "homeTeam.placeName.default",
    "periodDescriptor.periodType", "periodDescriptor.number",
)

STANDINGS_KEYS = (
    "points", "gamesPlayed", "wins", "losses", "otLosses",
    "teamCommonName.default", "teamAbbrev.default", "teamName.default",
    "conferenceSequence", "conferenceName", "divisionSequence", "divisionName",
    "gameTypeId", "leagueSequence", "seasonId", "streakCode", "streakCount",
    "l10Wins", "l10Losses", "l10OtLosses", "wildcardSequence",
)


def test_ping():
    assert ping_nhl_api()["data"] is not None, "stats REST ping did not answer"


def test_seasons():
    seasons = tailored_seasons()["data"]
    assert seasons, "season list is empty"
    ids = [s["id"] for s in seasons]
    assert ids == sorted(ids, reverse=True), "seasons are no longer sorted newest first"
    assert PAST_SEASON in ids


def test_season_state_is_derivable(season_state):
    assert season_state["state"] in ("offseason", "preseason", "regular", "playoffs"), season_state
    assert season_state["season_start"], "current season has no start date"


# --- scores --------------------------------------------------------------------

def test_scores_today_envelope():
    raw = fetch_scores()
    assert raw, "fetch_scores() for today returned nothing"
    check_keys(raw["data"], "currentDate", "games", where="/score/today")
    tailored_scores()


def test_scores_regular_season_shape():
    raw = fetch_scores(REGULAR_SEASON_DATE)
    assert raw, f"fetch_scores({REGULAR_SEASON_DATE}) returned nothing"
    games = raw["data"]["games"]
    assert games, f"no games on {REGULAR_SEASON_DATE}"
    for game in games:
        check_keys(game, *SCORE_GAME_KEYS, where=f"score game {game.get('id')}")
        assert game["gameType"] == 2

    tailored = tailored_scores(REGULAR_SEASON_DATE)
    assert tailored["currentDate"] == REGULAR_SEASON_DATE
    assert len(tailored["data"]) == len(games)
    for game in tailored["data"]:
        assert game["awayTeam"]["name"] and game["homeTeam"]["name"]


def test_scores_playoffs_carry_series_status():
    games = tailored_scores(PLAYOFF_DATE)["data"]
    assert games, f"no games on {PLAYOFF_DATE}"
    for game in games:
        assert game["gameType"] == 3
        status = game.get("seriesStatus")
        assert status, f"playoff game {game['id']} has no seriesStatus"
        check_keys(status, "round", "topSeedTeamAbbrev", "topSeedWins",
                   "bottomSeedTeamAbbrev", "bottomSeedWins", where="seriesStatus")


# --- games ---------------------------------------------------------------------

def test_game_landing_shape():
    data = fetch(REGULAR_SEASON_GAME_ID)["data"]
    assert data, f"landing for {REGULAR_SEASON_GAME_ID} returned nothing"
    check_keys(data, *LANDING_KEYS, where="gamecenter landing")


def test_game_init():
    game = Game(gameid=REGULAR_SEASON_GAME_ID, delay=0)
    assert game.init_game(), "Game.init_game() did not complete"
    assert game.away_team_abbrev and game.home_team_abbrev
    assert game.game_outcome, "finished game has no outcome"
    assert game.away_team_record and game.home_team_record, "team records were not built from team stats"


# --- standings -----------------------------------------------------------------

def test_standings_shape():
    raw = fetch_standings()["data"]
    if not raw:
        pytest.skip("standings/now is empty")
    for team in raw:
        check_keys(team, *STANDINGS_KEYS, where=f"standings {team.get('teamAbbrev')}")

    tailored = tailored_standings()
    wildcard = sort_wildcard_standings(tailored)
    assert len(wildcard) == 2, f"expected 2 conferences, got {list(wildcard)}"


def test_standings_teams_match_known_teams():
    raw = fetch_standings()["data"]
    if not raw:
        pytest.skip("standings/now is empty")
    api_teams = {team["teamAbbrev"]["default"] for team in raw}
    known = set(get_all_team_abbrevs())
    assert api_teams == known, (
        f"team list changed -- new on API: {sorted(api_teams - known)}, "
        f"no longer on API: {sorted(known - api_teams)}"
    )


# --- teams, rosters, schedule --------------------------------------------------

def test_roster_shape():
    roster = fetch_team_roster("MTL")
    assert roster, "roster fetch failed"
    check_keys(roster["data"], "forwards", "defensemen", "goalies", where="roster")
    assert roster["data"]["forwards"], "roster has no forwards"


def test_season_schedule_shape():
    games = fetch_season_schedule("MTL")
    assert games, "club-schedule-season returned no games"
    for game in games:
        check_keys(game, "id", "gameDate", "gameType", "gameState", "gameScheduleState",
                   where=f"schedule game {game.get('id')}")


def test_team():
    team = Team("Canadiens")
    assert team.abbrev == "MTL"
    stats = team.get_team_stats(season=PAST_SEASON)
    check_keys(stats, "wins", "losses", "otLosses", where="team summary")


# --- leaders -------------------------------------------------------------------

@pytest.mark.parametrize("stat_type, category", [
    ("goals", "skaters"),
    ("assists", "skaters"),
    ("points", "skaters"),
    ("savePctg", "goalies"),
])
def test_leaders(stat_type, category):
    raw = fetch_leaders(stat_type, category, season=PAST_SEASON)["leaders"]
    assert raw, f"no {category} leaders for {stat_type}"
    check_keys(raw[0], stat_type, "player.id", "player.firstName", "player.lastName",
               "player.positionCode", "player.sweaterNumber", "player.currentTeamId",
               "team.fullName", "team.triCode", where=f"{category}/{stat_type} leader")
    assert tailored_leaders(stat_type, category, season=PAST_SEASON)["data"]
