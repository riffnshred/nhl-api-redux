import datetime
from .domains import BASE
import requests
from requests.exceptions import HTTPError, ConnectionError, Timeout
import json
from datetime import datetime, timezone, date
import time
from .logger import logger

"""
    Useful endpoints

    Season details by seasonid: https://api.nhle.com/stats/rest/en/season?cayenneExp=id={seasonid}
    Season ordered by id in decending order: https://api.nhle.com/stats/rest/en/season?sort=[{"property":"id","direction":"DESC"}]
    
"""


def fetch_seasons():
    url = f'{BASE}/stats/rest/en/season'
    data = []
    params = {
        "sort": '[{"property":"id","direction":"DESC"}]'
    }
    response = requests.get(url, params=params)
    response.raise_for_status()  # Raise an exception if the response status code is not in the 2xx range (e.g., 200 OK)
    json_response = response.json()
    if 'data' in json_response:
        data = json_response["data"]
    else:
        logger.warning("'data' not found in seasons response")
            
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")    
    return {"timestamp":timestamp, "data":data}

def tailored_seasons():
    raw_seasons = fetch_seasons()
    timestamp = raw_seasons.get("timestamp")
    raw_data = raw_seasons.get("data",[])
    
    tailored_data = [
        {
            "id": season_details["id"],
            "conferencesInUse": season_details["conferencesInUse"],
            "divisionsInUse": season_details["divisionsInUse"],
            "endDate": season_details["endDate"],
            "formattedSeasonId": season_details["formattedSeasonId"],
            "numberOfGames": season_details["numberOfGames"],
            "preseasonStartdate": season_details["preseasonStartdate"],
            "regularSeasonEndDate": season_details["regularSeasonEndDate"],
            "seasonOrdinal": season_details["seasonOrdinal"],
            "startDate": season_details["startDate"],
            "wildcardInUse": season_details["wildcardInUse"]
        } 
        for season_details in raw_data
    ]
    
    return {"timestamp": timestamp, "data": tailored_data}


def get_current_season_details(seasons_data=None):
    seasons = tailored_seasons() if seasons_data is None else seasons_data
    return seasons["data"][0]

def get_current_season(seasons_data=None):
    seasons = tailored_seasons() if seasons_data is None else seasons_data
    return seasons["data"][0]["id"]

def get_previous_season_id(season_id):
    """Return the id of the season before `season_id` (20262027 -> 20252026)."""
    start_year = int(str(season_id)[:4])
    return int(f"{start_year - 1}{start_year}")

# This is a fail safe function that will return what should be the current nhl season id. 
# This is in case the api does not respond.

def guess_current_season():
    today = date.today()
    if today.month < 9:  # NHL season starts in October
        start_year = today.year - 1
    else:
        start_year = today.year
    end_year = start_year + 1
    return int(f"{start_year}{end_year}")

def _season_date(season_details, key):
    """Parse a date field out of a season descriptor. Returns None if absent or unparseable."""
    raw = season_details.get(key)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        logger.warning("Could not parse season date %s=%r", key, raw)
        return None

def get_season_state(season_details=None, today=None):
    """
    Derive the current phase of the NHL season from a season descriptor.

    The API hands out dates but never a phase, so we work it out from the four
    boundary dates it does give us.

    Args:
        season_details: A descriptor from tailored_seasons()["data"]. Fetched live
            if omitted.
        today: Date to evaluate against. Defaults to the local current date.

    Returns:
        Dict with the season id, the derived `state` (offseason/preseason/regular/
        playoffs), `days_until_season` (int before the season starts, None once it
        is under way), and the boundary dates as plain YYYY-MM-DD strings.
    """
    if season_details is None:
        season_details = get_current_season_details()
    if today is None:
        today = date.today()

    preseason_start = _season_date(season_details, "preseasonStartdate")
    season_start = _season_date(season_details, "startDate")
    regular_end = _season_date(season_details, "regularSeasonEndDate")
    season_end = _season_date(season_details, "endDate")

    if season_start and today < season_start:
        state = "preseason" if preseason_start and today >= preseason_start else "offseason"
    elif regular_end and today <= regular_end:
        state = "regular"
    elif season_end and today <= season_end:
        state = "playoffs"
    else:
        state = "offseason"

    # Only counted down before the puck drops. Once the season is under way the start
    # date is behind us, and in the offseason tail the API may not have published the
    # next season yet -- in both cases there is no honest number to report.
    days_until_season = None
    if state in ("offseason", "preseason") and season_start:
        remaining = (season_start - today).days
        if remaining >= 0:
            days_until_season = remaining

    return {
        "season_id": season_details.get("id"),
        "season": season_details.get("formattedSeasonId"),
        "state": state,
        "days_until_season": days_until_season,
        "preseason_start": preseason_start.isoformat() if preseason_start else None,
        "season_start": season_start.isoformat() if season_start else None,
        "regular_season_end": regular_end.isoformat() if regular_end else None,
        "season_end": season_end.isoformat() if season_end else None,
        "number_of_games": season_details.get("numberOfGames"),
    }
