import requests
import json
from datetime import datetime, timezone
from .domains import BASEWEB
from .examples import load_exemple

EMPTY_STANTINGS = {"wildCardIndicator":False}

def fetch_standings():
    url = f"{BASEWEB}/standings/now"
    data = []
    response = requests.get(url)
    response.raise_for_status()  # Raise an exception if the response status code is not in the 2xx range (e.g., 200 OK)
    data = response.json()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"timestamp":timestamp, "data":data["standings"]}

def fetch_empty_standings():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")    
    return {"timestamp":timestamp, "data":EMPTY_STANTINGS["standings"]}

def fetch_standings_exemple():
    """Return the bundled sample standings payload, for offline development."""
    data = load_exemple("standings_exemple.json")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"timestamp":timestamp, "data":data["standings"]}
 

# tailored standings translate a lean standing data set into a predetermined key/value pair. 
# This is to provide a more robust set of data for the clients and make it easier to provide a fix in case the NHL API changes its structure.   
def tailored_standings():
    raw_standings = fetch_standings()
    timestamp = raw_standings.get("timestamp")
    raw_data = raw_standings.get("data", [])
    
    tailored_data = [
        {
            "points": team_record["points"],
            "gamesPlayed": team_record["gamesPlayed"],
            "wins": team_record["wins"],
            "losses": team_record["losses"],
            "otLosses": team_record["otLosses"],
            "teamCommonName": team_record["teamCommonName"]["default"],
            "team_abbrev" : team_record["teamAbbrev"]["default"],
            "teamName": team_record["teamName"]["default"],
            "conferenceSequence": team_record["conferenceSequence"],
            "conferenceName": team_record["conferenceName"],
            "divisionSequence": team_record["divisionSequence"],
            "divisionName": team_record["divisionName"],
            "gameTypeId": team_record["gameTypeId"],
            "leagueSequence": team_record["leagueSequence"],
            "seasonId": team_record["seasonId"],
            "streakCode": team_record["streakCode"],
            "streakCount": team_record["streakCount"],
            "l10Wins": team_record["l10Wins"],
            "l10Losses": team_record["l10Losses"],
            "l10OtLosses": team_record["l10OtLosses"],
            "wildcardSequence": team_record["wildcardSequence"],
            "wins": team_record["wins"]
        }for team_record in raw_data
    ]
    
    return {"timestamp": timestamp, "data": tailored_data}

"""
    Sorting functions

    Reorganize the raw standing data into respective type of standings.
    
    Param:
        - standings = raw standings data
        - lean = if set to true, the function will filter the data of each team and only keep the basic info (Points, W-L-OTL, Last 10, Streak).
""" 
   
""" 
NOTE: Not being used at the moment but saving for later as it might be useful.

def filter_team_standing_data(team_data):
    filtered_keys = [
        "conferenceSequence",
        "conferenceName",
        "divisionSequence",
        "divisionName",
        "gameTypeId",
        "gamesPlayed",
        "leagueSequence",
        "losses",
        "otLosses",
        "points",
        "seasonId",
        "streakCode",
        "streakCount",
        "teamName",
        "teamCommonName",
        "teamAbbrev",
        "wildcardSequence",
        "wins"
    ]  # Add more keys if needed in the future

    filtered_dict = {key: team_data[key] for key in filtered_keys if key in team_data}
    return filtered_dict 
    
"""

def sort_league_standings(standings_data=None):
    # If Standings data is provided, use that. Otherwise, request it from the API
    standings = tailored_standings() if standings_data is None else standings_data
    
    league = {"league":[]}
    for team in standings["data"]:
        league["league"].append(team)
        
    return league

def sort_division_standings(standings_data=None):
    # If Standings data is provided, use that. Otherwise, request it from the API
    standings = tailored_standings() if standings_data is None else standings_data
    
    divisions = {}
    for team in standings["data"]:
        division_name = team["divisionName"].lower()
        if division_name not in divisions:
            divisions[division_name] = []
                        
        divisions[division_name].append(team)
    return divisions

def sort_conference_standings(standings_data=None):
    # If Standings data is provided, use that. Otherwise, request it from the API
    standings = tailored_standings() if standings_data is None else standings_data
    
    conferences = {}
    for team in standings["data"]:
        conference_name = team["conferenceName"].lower()
        if conference_name not in conferences:
            conferences[conference_name] = []
            
        conferences[conference_name].append(team)
        
    return conferences

def sort_wildcard_standings(standings_data=None):

    # If Standings data is provided, use that. Otherwise, request it from the API
    standings = tailored_standings() if standings_data is None else standings_data

    # First pass: collect divisions and wildcard per conference
    conferences = {}
    for team in standings["data"]:
        conference_name = team["conferenceName"].lower()
        division_name = team["divisionName"].lower()
        if conference_name not in conferences:
            conferences[conference_name] = {"divisions": {}, "wildcard": []}
        if division_name not in conferences[conference_name]["divisions"]:
            conferences[conference_name]["divisions"][division_name] = []

        if team["wildcardSequence"] == 0:
            conferences[conference_name]["divisions"][division_name].append(team)
        else:
            conferences[conference_name]["wildcard"].append(team)

    # Second pass: build with correct key order (divisions first, wildcard last)
    wildcard = {}
    for conference_name, conf_data in conferences.items():
        wildcard[conference_name] = {}
        for division_name, teams in conf_data["divisions"].items():
            wildcard[conference_name][division_name] = teams
        wildcard[conference_name]["wildcard"] = sorted(
            conf_data["wildcard"], key=lambda t: t["wildcardSequence"]
        )
    return wildcard
