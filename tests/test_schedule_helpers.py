"""
Tests for the schedule helpers that pick a team's previous and next game.

No network here: the schedules are built by hand around today's date.
"""

from datetime import date, timedelta

from nhl_api_redux.teams import find_previous_and_next_games


def _game(game_id, days_from_today, state="FUT", schedule_state="OK"):
    return {
        "id": game_id,
        "gameDate": (date.today() + timedelta(days=days_from_today)).isoformat(),
        "gameState": state,
        "gameScheduleState": schedule_state,
    }


def _ids(schedule):
    previous_game, next_game = find_previous_and_next_games(schedule)
    return (previous_game and previous_game["id"], next_game and next_game["id"])


def test_next_game_is_the_upcoming_one_on_an_off_day():
    schedule = [_game(1, -1, "OFF"), _game(2, 1), _game(3, 4)]
    assert _ids(schedule) == (1, 2)


def test_next_game_is_todays_game_before_it_starts():
    for state in ("FUT", "PRE"):
        schedule = [_game(1, -2, "OFF"), _game(2, 0, state), _game(3, 3)]
        assert _ids(schedule) == (1, 2)


def test_live_game_is_neither_previous_nor_next():
    schedule = [_game(1, -2, "OFF"), _game(2, 0, "LIVE"), _game(3, 3)]
    assert _ids(schedule) == (1, 3)


def test_finished_game_today_becomes_the_previous_game():
    schedule = [_game(1, -2, "OFF"), _game(2, 0, "FINAL"), _game(3, 3)]
    assert _ids(schedule) == (2, 3)


def test_postponed_game_is_skipped():
    schedule = [_game(1, -2, "OFF"), _game(2, 1, "FUT", "PPD"), _game(3, 3)]
    assert _ids(schedule) == (1, 3)


def test_first_and_last_games_of_the_season():
    assert _ids([_game(1, 2), _game(2, 4)]) == (None, 1)
    assert _ids([_game(1, -2, "OFF"), _game(2, 1)]) == (1, 2)
