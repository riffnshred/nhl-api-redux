import requests
import json
from datetime import datetime, timezone
from .domains import BASEWEB

EMPTY_STANTINGS = {"wildCardIndicator":False, "standings":[]}

def fetch_standings():
    url = f"{BASEWEB}/standings/now"
    data = None
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception if the response status code is not in the 2xx range (e.g., 200 OK)
        data = response.json()

    except requests.exceptions.RequestException as e:
        print(f"Request to {url} failed: {e}")
        
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")    
    return {"timestamp":timestamp, "data":data["standings"]}

def fetch_empty_standings():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")    
    return {"timestamp":timestamp, "data":EMPTY_STANTINGS}

def fetch_standings_exemple():
    with open("nhl_api_redux/endpoint_exemple/standings_exemple.json", 'r') as file:
        data = json.load(file)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")    
        return {"timestamp":timestamp, "data":data["standings"]}
    
    
"""
    Sorting functions

    Reorganize the raw standing data into respective type of standings.
    
    Param:
        - standings = raw standings data
        - lean = if set to true, the function will filter the data of each team and only keep the basic info (Points, W-L-OTL, Last 10, Streak).
"""    
def filter_team_standing_data(team_data):
    filtered_keys = [
        "date",
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

def sort_league_standings(standings, lean=False):
    league = {"league":[]}
    for team in standings["data"]:
        if lean:
            team = filter_team_standing_data(team)
        league["league"].append(team)
        
    return league

def sort_division_standings(standings, lean=False):
    divisions = {}
    for team in standings["data"]:
        division_name = team["divisionName"].lower()
        if division_name not in divisions:
            divisions[division_name] = []
            
        if lean:
            team = filter_team_standing_data(team)
            
        divisions[division_name].append(team)
    return divisions

def sort_conference_standings(standings, lean=False):
    conferences = {}
    for team in standings["data"]:
        conference_name = team["conferenceName"].lower()
        if conference_name not in conferences:
            conferences[conference_name] = []
            
        if lean:
            team = filter_team_standing_data(team)
            
        conferences[conference_name].append(team)
        
    return conferences

def sort_wildcard_standings(standings, lean=False):
    wildcard = {}
    for team in standings["data"]:
        conference_name = team["conferenceName"].lower()
        division_name = team["divisionName"].lower()
        if conference_name not in wildcard:
            wildcard[conference_name] = {"wildcard":[]}
            
        if division_name not in wildcard[conference_name]:
            wildcard[conference_name][division_name] = []
        
        if lean:
            team = filter_team_standing_data(team)
        
        if team["wildcardSequence"] == 0:
            wildcard[conference_name][division_name].append(team)
        else:
            wildcard[conference_name]["wildcard"].append(team)
    return wildcard




def test_standings(standing_type="division"):
    standings = fetch_standings()
    print(standings)
    division_standings = filter_division_standings(standings["data"])
    conference_standings = filter_conference_standings(standings["data"])
    wildcard_standings = filter_wildcard_standings(standings["data"])

    if standing_type == "division":
        for division, teams in division_standings.items():
            print(f"Division: {division}")
            print("-------------------")
            for team in teams:
                team_name = team['placeName']['default']
                points = team['points']
                sequence = team["divisionSequence"]
                print(f"{sequence} - {team_name}: {points} points")
            print()
            
    if standing_type == "conference":
        for conference, teams in conference_standings.items():
            print(f"Conference: {conference}")
            print("-------------------")
            for team in teams:
                print(f"{team['conferenceSequence']} - {team['teamName']['default']}: {team['points']}")
                # Print other relevant information as needed
            print()
    
    if standing_type == "wildcard":
        for conference, divisions in wildcard_standings.items():
            print(f"{conference}")
            print("-------------------")
            for d, teams in divisions.items():
                print(f"{d}")
                print("-------------------")
                for team in teams:
                    team_name = team['placeName']['default']
                    points = team['points']
                    if d == "Wildcard":
                        sequence = team["wildcardSequence"]
                    else:
                        sequence = team["divisionSequence"]
                    print(f"{sequence} - {team_name}: {points} points")
                print()
            print()