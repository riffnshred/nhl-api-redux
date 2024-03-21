import datetime
from .domains import BASE
import requests
import json
from datetime import datetime, timezone, date

def fetch_seasons():
    url = f"{BASE}/stats/rest/en/season"
    data = None
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception if the response status code is not in the 2xx range (e.g., 200 OK)
        data = response.json()

    except requests.exceptions.RequestException as e:
        print(f"Request to {url} failed: {e}")
        
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")    
    return {"timestamp":timestamp, "data":data["data"]}


def filter_seasons_data(seasons_data):
    filtered_keys = [
        "id",
        "endDate",
        "numberOfGames",
        "preseasonStartdate",
        "regularSeasonEndDate",
        "startDate",
        "formattedSeasonId"
    ]  # Add more keys if needed in the future

    filtered_data = {key: seasons_data[key] for key in filtered_keys if key in seasons_data}
    return filtered_data

def get_previous_season_details(seasons_data=None, lean=False):
    seasons = fetch_seasons() if seasons_data is None else seasons_data
    previous_season = seasons["data"][-2]
    if lean:
        previous_season = filter_seasons_data(previous_season)
    
    return current_season

def get_current_season_details(seasons_data=None, lean=False):
    seasons = fetch_seasons() if seasons_data is None else seasons_data
    current_season = seasons["data"][-1]
    if lean:
        current_season = filter_seasons_data(current_season)
    
    return current_season

def get_current_season(seasons_data=None):
    seasons = fetch_seasons() if seasons_data is None else seasons_data
    return seasons["data"][-1]["id"]

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