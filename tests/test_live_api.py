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
from nhl_api_redux import scores as scores_module
from nhl_api_redux.scores import fetch_scores, fetch_scoreboard, tailored_scores
from nhl_api_redux.seasons import tailored_seasons
from nhl_api_redux.server import ping_nhl_api
from nhl_api_redux.standings import (
    fetch_standings,
    sort_wildcard_standings,
    tailored_standings,
)
from nhl_api_redux.teams import Team, fetch_season_schedule, get_all_team_abbrevs, teams_info

# A completed season with data that will not move.
PAST_SEASON = 20242025
REGULAR_SEASON_DATE = "2025-03-15"
PLAYOFF_DATE = "2025-05-01"
REGULAR_SEASON_GAME_ID = 2024020500

# Fields both endpoints must agree on for the same game, whatever its state.
FALLBACK_STABLE_KEYS = ("season", "gameType", "startTimeUTC", "gameScheduleState")
FALLBACK_STABLE_TEAM_KEYS = ("id", "abbrev", "name")
# Fields the scoreboard drops once a game is over, or that move between two
# fetches of a game in progress.
FALLBACK_VOLATILE_KEYS = ("clock", "period", "periodDescriptor")
IN_PROGRESS = ("LIVE", "CRIT")

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


def _fallback_scores(monkeypatch, date=None):
    """tailored_scores' fallback path, with score/ forced to fail."""
    monkeypatch.setattr(scores_module, "fetch_scores", lambda *a, **k: None)
    return tailored_scores(date, fallback=True, fallback_max_retries=2)


def test_scoreboard_carries_the_requested_day():
    raw = fetch_scoreboard(REGULAR_SEASON_DATE)
    assert raw, f"fetch_scoreboard({REGULAR_SEASON_DATE}) returned nothing"
    check_keys(raw["data"], "gamesByDate", where="/scoreboard")
    days = raw["data"]["gamesByDate"]
    assert days, "scoreboard carries no days at all"
    # The day is selected by matching the date, never by trusting focusedDate.
    day = next((d for d in days if d.get("date") == REGULAR_SEASON_DATE), None)
    assert day, (f"scoreboard/{REGULAR_SEASON_DATE} does not carry that date; "
                 f"it covers {[d.get('date') for d in days]}")
    assert day["games"], f"no games on {REGULAR_SEASON_DATE}"


def test_scores_fallback_matches_the_score_endpoint(monkeypatch):
    """
    The fallback reproduces tailored_scores for the same date.

    Games in progress are compared on their stable fields only: the two payloads
    are fetched moments apart, so a clock or a shot total is allowed to move.
    """
    today = scores_module.get_current_date()
    primary = tailored_scores(today)
    assert primary is not None, "tailored_scores() for today returned nothing"
    fallback = _fallback_scores(monkeypatch, today)
    assert fallback is not None, "the scoreboard fallback for today returned nothing"

    if not primary["data"]:
        pytest.skip("no games today")

    assert fallback["currentDate"] == primary["currentDate"]

    scored = {game["id"]: game for game in primary["data"]}
    fell_back = {game["id"]: game for game in fallback["data"]}
    assert set(scored) == set(fell_back), (
        f"score/ and scoreboard/ disagree on today's slate: "
        f"only in score/ {sorted(set(scored) - set(fell_back))}, "
        f"only in scoreboard/ {sorted(set(fell_back) - set(scored))}"
    )

    for game_id, want in scored.items():
        got = fell_back[game_id]
        where = f"game {game_id} ({want['gameState']})"
        for key in FALLBACK_STABLE_KEYS:
            assert got[key] == want[key], f"{where}: {key} is {got[key]!r}, score/ says {want[key]!r}"
        for side in ("awayTeam", "homeTeam"):
            for key in FALLBACK_STABLE_TEAM_KEYS:
                assert got[side][key] == want[side][key], (
                    f"{where}: {side}.{key} is {got[side][key]!r}, score/ says {want[side][key]!r}")
            assert got[side]["record"] == want[side]["record"], f"{where}: {side}.record"

        # Finished games lose their shots and clock on the scoreboard, and a game
        # in progress moves between the two fetches.
        if want["gameState"] != got["gameState"] or want["gameState"] in IN_PROGRESS:
            continue
        if want["gameState"] in ("FINAL", "OFF"):
            continue
        for key in FALLBACK_VOLATILE_KEYS:
            assert got[key] == want[key], f"{where}: {key} is {got[key]!r}, score/ says {want[key]!r}"
        for side in ("awayTeam", "homeTeam"):
            for key in ("score", "sog"):
                assert got[side][key] == want[side][key], f"{where}: {side}.{key}"


def test_scores_fallback_names_are_nicknames(monkeypatch):
    fallback = _fallback_scores(monkeypatch)
    assert fallback is not None, "the scoreboard fallback for today returned nothing"
    if not fallback["data"]:
        pytest.skip("no games today")

    for game in fallback["data"]:
        for side in ("awayTeam", "homeTeam"):
            team = game[side]
            known = teams_info.get(str(team["id"]))
            assert team["name"], f"game {game['id']} {side} has no name"
            if known:
                assert team["name"] == known["name"], (
                    f"game {game['id']} {side} is {team['name']!r}, expected the "
                    f"nickname {known['name']!r}")
                assert team["name"] != known["fullName"], (
                    f"game {game['id']} {side} carries the full name; "
                    f"format_scores_for_display downstream keys off the nickname")


def test_scores_fallback_shape_is_thinner_but_stable(monkeypatch):
    fallback = _fallback_scores(monkeypatch)
    assert fallback is not None, "the scoreboard fallback for today returned nothing"
    if not fallback["data"]:
        pytest.skip("no games today")

    for game in fallback["data"]:
        assert game["goals"] == [], "the scoreboard has no goal summaries to carry"
        assert "seriesStatus" not in game, "the scoreboard has no seriesStatus to carry"


def test_scores_source_key_marks_the_fallback(monkeypatch):
    """`source` appears only when the fallback produced the data."""
    healthy = tailored_scores()
    assert healthy is not None, "tailored_scores() for today returned nothing"
    assert "source" not in healthy, "a healthy score/ fetch must not be labelled"

    monkeypatch.setattr(scores_module, "fetch_scores", lambda *a, **k: None)
    assert tailored_scores() is None, "a failed fetch without fallback=True must return None"

    degraded = tailored_scores(fallback=True)
    assert degraded is not None, "the fallback did not run"
    assert degraded["source"] == "scoreboard"
    assert sorted(degraded) == ["currentDate", "data", "source", "timestamp"]


def test_scores_return_none_when_both_endpoints_fail(monkeypatch):
    monkeypatch.setattr(scores_module, "fetch_scores", lambda *a, **k: None)
    monkeypatch.setattr(scores_module, "fetch_scoreboard", lambda *a, **k: None)
    assert tailored_scores(fallback=True) is None


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
