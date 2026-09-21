import requests
import json
from datetime import datetime, timezone
from .domains import BASEWEB, DEFAULT_TIMEOUT, FALLBACK_TIMEOUT
from .http import _get
from .logger import logger
from .examples import load_exemple
from .teams import teams_info
import time

EMPTY_SCORES = {
   "prevDate":"2023-06-13",
   "currentDate":"2023-08-18",
   "nextDate":"2023-09-23",
   "gameWeek":[
      {
         "date":"2023-08-15",
         "dayAbbrev":"TUE",
         "numberOfGames":0
      },
      {
         "date":"2023-08-16",
         "dayAbbrev":"WED",
         "numberOfGames":0
      },
      {
         "date":"2023-08-17",
         "dayAbbrev":"THU",
         "numberOfGames":0
      },
      {
         "date":"2023-08-18",
         "dayAbbrev":"FRI",
         "numberOfGames":0
      },
      {
         "date":"2023-08-19",
         "dayAbbrev":"SAT",
         "numberOfGames":0
      },
      {
         "date":"2023-08-20",
         "dayAbbrev":"SUN",
         "numberOfGames":0
      },
      {
         "date":"2023-08-21",
         "dayAbbrev":"MON",
         "numberOfGames":0
      }
   ],
   "games":[
      
   ]
}

def get_current_date():
    return datetime.now().strftime("%Y-%m-%d")

def _resolve_date(date, label="Scores"):
    """Validate a YYYY-MM-DD date, or return today's when none was given."""
    if not date:
        return get_current_date()
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Error - {label} - Fetch - Wrong date format provided, must be YYYY-MM-DD")
    return date

def _fetch_json(url, label, max_retries, retry_delay, timeout):
    """
    GET a JSON payload, retrying transient failures.

    Returns {"timestamp": ..., "data": ...} on success, or None when every attempt
    failed.
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = _get(url, timeout=timeout)
            response.raise_for_status()

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return {"timestamp": timestamp, "data": response.json()}
        except requests.exceptions.RequestException as req_err:
            # Covers HTTP errors, timeouts, connection failures and malformed JSON
            # bodies alike (JSONDecodeError is a RequestException) - all of them are
            # worth another try.
            logger.warning("%s fetch failed: %s - Retrying (%d/%d)...",
                           label, req_err, attempt, max_retries)

        if attempt < max_retries:
            time.sleep(retry_delay)

    logger.error("%s fetch failed after %d attempts: %s", label, max_retries, url)
    return None

# Get the scores off the API. If a data is provided it need to be
def fetch_scores(date=None, max_retries=3, retry_delay=1, debug_data=None,
                 timeout=DEFAULT_TIMEOUT):
    """
    Fetch the raw score payload for a date.

    Returns {"timestamp": ..., "data": ...} on success, or None when every attempt
    failed. None means "we could not find out", which is not the same as a day with no
    games: callers on a poll loop should hold their last known value rather than
    publish an empty scoreboard over a good one.

    Raises ValueError if `date` is not YYYY-MM-DD.
    """
    # If debug_data is True, return example data instead of making API call
    if debug_data:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"timestamp": timestamp, "data": debug_data}

    date = _resolve_date(date)

    return _fetch_json(f"{BASEWEB}/score/{date}", "Scores",
                       max_retries, retry_delay, timeout)

def fetch_scoreboard(date=None, max_retries=1, retry_delay=1,
                     timeout=FALLBACK_TIMEOUT):
    """
    Fetch the raw scoreboard payload for a date.

    `/v1/scoreboard/{date}` answers with `gamesByDate`, a list of {date, games}
    covering roughly a week around the date asked for. It carries the same live
    score, shots and clock as `/v1/score/{date}` but no goal summaries, and it
    stays up when that path does not -- which is what it is here for. See
    `tailored_scores(fallback=True)`.

    The dated form is the only one worth using: `scoreboard/now` resolves against
    the server's clock, which disagrees with the caller's date around the midnight
    rollover.

    Returns {"timestamp": ..., "data": ...} on success, or None when every attempt
    failed. Defaults are deliberately thinner than fetch_scores' -- one attempt on a
    short timeout -- because this runs inside a call that has already waited.

    Raises ValueError if `date` is not YYYY-MM-DD.
    """
    date = _resolve_date(date, label="Scoreboard")

    return _fetch_json(f"{BASEWEB}/scoreboard/{date}", "Scoreboard",
                       max_retries, retry_delay, timeout)

def fetch_empty_scores():
    return EMPTY_SCORES

def fetch_scores_exemple():
    """Return the bundled sample scores payload, for offline development."""
    return load_exemple("scores_exemple.json")

def _team_name(team):
    """
    The team's nickname ("Devils"), the way /v1/score/ spells it.

    teams_info is keyed by string id and is the source of truth, because the
    scoreboard payload carries the full name in `name` where score/ carries the
    nickname. It is a static table though, so a franchise that moves or arrives
    before this package is updated falls through to the payload.
    """
    return (teams_info.get(str(team.get("id")), {}).get("name")
            or team.get("commonName", {}).get("default")
            or team.get("name", {}).get("default"))

def _scoreboard_team(team):
    return {
        "id": team.get("id"),
        "abbrev": team.get("abbrev"),
        "name": _team_name(team),
        # FINAL games drop sog on this endpoint; the next healthy score/ poll
        # brings it back.
        "sog": team.get("sog"),
        "score": team.get("score"),
        "record": team.get("record", ""),
    }

def _scoreboard_game(game):
    """Map one scoreboard game into the shape tailored_scores builds."""
    return {
        "id": game.get("id"),
        "season": game.get("season"),
        "awayTeam": _scoreboard_team(game.get("awayTeam", {})),
        "homeTeam": _scoreboard_team(game.get("homeTeam", {})),
        "gameType": game.get("gameType"),
        "startTimeUTC": game.get("startTimeUTC"),
        "gameScheduleState": game.get("gameScheduleState"),
        "gameState": game.get("gameState"),
        # Also dropped on FINAL games here.
        "clock": game.get("clock", None),
        "period": game.get("period", None),
        "periodDescriptor": game.get("periodDescriptor", None),
        # The scoreboard has no goal summaries at all. Emit the key anyway so the
        # shape does not change under a caller, and leave seriesStatus off rather
        # than invent one for a playoff game.
        "goals": [],
    }

def _scoreboard_games(payload, date):
    """
    Pull one day's games out of a scoreboard payload.

    Returns the list of raw games for `date`, or None when the payload cannot
    speak to that date at all.

    The day is found by matching `date` against gamesByDate[].date -- never by
    trusting the top-level focusedDate. A day with nothing scheduled is simply
    absent from the list, so an absent date inside the span the payload covers
    means "no games", while one outside it means the endpoint answered about some
    other week and we still do not know.
    """
    days = payload.get("gamesByDate") or []
    for day in days:
        if day.get("date") == date:
            return day.get("games", [])

    dates = [day.get("date") for day in days if day.get("date")]
    if dates and min(dates) <= date <= max(dates):
        return []

    logger.error("Scoreboard fallback for %s came back covering %s to %s",
                 date, min(dates, default="?"), max(dates, default="?"))
    return None

def _scoreboard_fallback(date, max_retries, retry_delay, timeout):
    """
    Build a tailored_scores envelope out of the scoreboard endpoint.

    Returns None under the same rule as the primary: the caller must still be able
    to tell "could not find out" from "no games scheduled".
    """
    raw = fetch_scoreboard(date, max_retries=max_retries, retry_delay=retry_delay,
                           timeout=timeout)
    if raw is None:
        return None

    raw_games = _scoreboard_games(raw.get("data", {}), date)
    if raw_games is None:
        return None

    games = [_scoreboard_game(game) for game in raw_games]
    # A degraded success, not a healthy one -- and said once for the call, not
    # once per game.
    logger.warning("Scores for %s came from the scoreboard fallback: %d game(s), "
                   "no goal details%s", date, len(games),
                   ", no shots or clock on finished games" if games else "")
    return {"timestamp": raw.get("timestamp"), "currentDate": date, "data": games,
            "source": "scoreboard"}

# Fetch the Scores of the day and return a cleaner version.
def tailored_scores(date=None, debug_data=None, max_retries=3, retry_delay=1,
                    timeout=DEFAULT_TIMEOUT, fallback=False,
                    fallback_max_retries=1, fallback_timeout=FALLBACK_TIMEOUT):
    """
    Return a trimmed view of the day's scores, or None if the fetch failed.

    The None is passed straight through from fetch_scores so that a caller can tell
    an unreachable API apart from a day with no games on the schedule.

    With `fallback=True`, a failed /v1/score/ fetch is retried once against
    /v1/scoreboard/, which has stayed up through outages of that path. The reply
    then carries `"source": "scoreboard"` and is a little thinner: `goals` is
    always empty, playoff games carry no `seriesStatus`, and finished games lose
    `sog` and `clock` until the next healthy poll. score/ stays the primary --
    the fallback only runs once it has exhausted `max_retries` -- and None still
    means both endpoints failed.
    """
    raw_scores = fetch_scores(date, max_retries=max_retries, retry_delay=retry_delay,
                              debug_data=debug_data, timeout=timeout)
    if raw_scores is None:
        if not fallback:
            return None
        return _scoreboard_fallback(_resolve_date(date), fallback_max_retries,
                                    retry_delay, fallback_timeout)

    games = []
    scores_data = raw_scores.get("data", {})
    currentDate = scores_data.get("currentDate")
    for game in scores_data.get("games", []):
        goals = [
            {
                "period": goal.get("period"),
                "timeInPeriod": goal.get("timeInPeriod"),
                "playerId": goal.get("playerId"),
                "name": goal.get("name"),
                "assists": [
                    {
                        "playerId": assist.get("playerId"),
                        "name": assist.get("name", {}).get("default"),
                        "assistsToDate": assist.get("assistsToDate")
                    }
                    for assist in goal.get("assists", [])
                ]
            }
            for goal in game.get("goals", [])
        ]
        
        away_team = game.get("awayTeam", {})
        home_team = game.get("homeTeam", {})

        g = {
            "id": game.get("id"),
            "season": game.get("season"),
            "awayTeam": {
                "id": away_team.get("id"),
                "abbrev": away_team.get("abbrev"),
                "name": away_team["name"].get("default"),
                "sog": away_team.get("sog"),
                "score": away_team.get("score"),
                "record": away_team.get("record", ""),
            },
            "homeTeam": {
                "id": home_team.get("id"),
                "abbrev": home_team.get("abbrev"),
                "name": home_team["name"].get("default"),
                "sog": home_team.get("sog"),
                "score": home_team.get("score"),
                "record": home_team.get("record", ""),
            },
            "gameType": game.get("gameType"),
            "startTimeUTC": game.get("startTimeUTC"),
            "gameScheduleState": game.get("gameScheduleState"),
            "gameState": game.get("gameState"),
            "clock": game.get("clock", None),
            "period": game.get("period", None),
            "periodDescriptor": game.get("periodDescriptor", None),
            "goals": goals
        }
        
        # If it's a post season game, get the series status.
        if game["gameType"] == 3:
            try:
                g["seriesStatus"] = game.get("seriesStatus")
            except Exception:
                logger.debug("No series status found for playoff game")
        
        games.append(g)    
    return {"timestamp": raw_scores.get("timestamp"), "currentDate": currentDate, "data": games}

def refresh_scores(date=None):
    """Refresh scores data - simplified wrapper around tailored_scores"""
    scores_data = tailored_scores(date)
    return scores_data["data"]

    
def test(date=None, teamid=9):
    """Test function to check if favorite team is playing today"""
    try:
        scores_games = refresh_scores(date)
        
        # Check if any game involves the favorite team
        fav_team_playing = False
        for game in scores_games:
            away_team_id = game["awayTeam"]["id"]
            home_team_id = game["homeTeam"]["id"]
            
            if away_team_id == teamid or home_team_id == teamid:
                fav_team_playing = True
                logger.info("My Favorite team is playing today - game id %s", game['id'])
                break

        if not fav_team_playing:
            logger.info("My Favorite team is Off today")

        for game in scores_games:
            away_team_abbrev = game["awayTeam"]["abbrev"]
            home_team_abbrev = game["homeTeam"]["abbrev"]
            game_state = game["gameState"]

            logger.info("%s %s VS %s %s - State: %s", away_team_abbrev, game['awayTeam'].get('score',''), game['homeTeam'].get('score',''), home_team_abbrev, game_state)

    except Exception as e:
        logger.error("Scores Test failed! Error: %s", e)
        return False

    return True
