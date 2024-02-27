import datetime
from .domains import BASEWEB
import requests
import json
from datetime import datetime, timezone, date

def fetch_seasons():
    url = f"{BASEWEB}/season"
    data = None
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception if the response status code is not in the 2xx range (e.g., 200 OK)
        data = response.json()

    except requests.exceptions.RequestException as e:
        print(f"Request to {url} failed: {e}")
        
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")    
    return {"timestamp":timestamp, "data":data}

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

def get_current_season():
    seasons = fetch_seasons()
    try:
        current_season = seasons["data"][-1]
    except TypeError as e:
        print(f"Failed to grab current season from API. Guessing the current NHL season based on current date.")
        current_season = guess_current_season()
    return current_season

