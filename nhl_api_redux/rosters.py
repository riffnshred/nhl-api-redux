import requests
from datetime import datetime, timezone

from .domains import BASEWEB
from .http import _get
from .logger import logger

"""
NHL API Roster Endpoints

Team Roster (current): https://api-web.nhle.com/v1/roster/{team_abbrev}/current
Returns: Complete roster with forwards, defensemen, goalies
"""


def fetch_team_roster(team_abbrev):
    """
    Fetch current roster for a specific team

    Args:
        team_abbrev: Team abbreviation (e.g., "TOR", "MTL", "BOS")

    Returns:
        Dict with timestamp and roster data, or None if failed
    """
    url = f"{BASEWEB}/roster/{team_abbrev}/current"

    try:
        response = _get(url)
        response.raise_for_status()
        data = response.json()

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "timestamp": timestamp,
            "team_abbrev": team_abbrev,
            "data": data
        }

    except requests.exceptions.RequestException as e:
        logger.warning("Failed to fetch roster for %s: %s", team_abbrev, e)
        return None


def fetch_all_rosters(team_abbrevs):
    """
    Fetch rosters for multiple teams

    Args:
        team_abbrevs: List of team abbreviations

    Returns:
        Dict mapping team abbreviation to roster data
    """
    rosters = {}

    for abbrev in team_abbrevs:
        roster_data = fetch_team_roster(abbrev)
        if roster_data:
            rosters[abbrev] = roster_data

    return rosters
