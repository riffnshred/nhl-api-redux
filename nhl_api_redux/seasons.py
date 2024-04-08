import datetime
from .domains import BASE
import requests
from requests.exceptions import HTTPError, ConnectionError, Timeout
import json
from datetime import datetime, timezone, date
import time

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
        print(f"'data' not found in the response")
            
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