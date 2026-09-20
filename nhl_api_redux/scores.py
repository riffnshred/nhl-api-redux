import requests
import json
from datetime import datetime, timezone
from .domains import BASEWEB, DEFAULT_TIMEOUT
from .logger import logger
from .examples import load_exemple
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

    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Error - Scores - Fetch - Wrong date format provided, must be YYYY-MM-DD")
    else:
        date = get_current_date()

    date_url = f"{BASEWEB}/score/{date}"

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(date_url, timeout=timeout)
            response.raise_for_status()

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return {"timestamp": timestamp, "data": response.json()}
        except requests.exceptions.RequestException as req_err:
            # Covers HTTP errors, timeouts, connection failures and malformed JSON
            # bodies alike (JSONDecodeError is a RequestException) - all of them are
            # worth another try.
            logger.warning("Scores fetch failed: %s - Retrying (%d/%d)...",
                           req_err, attempt, max_retries)

        if attempt < max_retries:
            time.sleep(retry_delay)

    logger.error("Scores fetch failed after %d attempts: %s", max_retries, date_url)
    return None

def fetch_empty_scores():
    return EMPTY_SCORES

def fetch_scores_exemple():
    """Return the bundled sample scores payload, for offline development."""
    return load_exemple("scores_exemple.json")

# Fetch the Scores of the day and return a cleaner version.
def tailored_scores(date=None, debug_data=None, max_retries=3, retry_delay=1,
                    timeout=DEFAULT_TIMEOUT):
    """
    Return a trimmed view of the day's scores, or None if the fetch failed.

    The None is passed straight through from fetch_scores so that a caller can tell
    an unreachable API apart from a day with no games on the schedule.
    """
    raw_scores = fetch_scores(date, max_retries=max_retries, retry_delay=retry_delay,
                              debug_data=debug_data, timeout=timeout)
    if raw_scores is None:
        return None

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
