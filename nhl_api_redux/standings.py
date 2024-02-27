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
    

def get_division_standings(standings):
    divisions = {}
    for team in standings:
        division_name = team["divisionName"]
        if division_name not in divisions:
            divisions[division_name] = []
        divisions[division_name].append(team)
        
    return divisions

def get_conference_standings(standings):
    conferences = {}
    for team in standings:
        conference_name = team["conferenceName"]
        if conference_name not in conferences:
            conferences[conference_name] = []
        conferences[conference_name].append(team)
        
    return conferences

def get_wildcard_standings(standings):
    wildcard = {}
    for team in standings:
        conference_name = team["conferenceName"]
        division_name = team["divisionName"]
        if conference_name not in wildcard:
            wildcard[conference_name] = {"Wildcard":[]}
            
        if division_name not in wildcard[conference_name]:
            wildcard[conference_name][division_name] = []
        
        if team["wildcardSequence"] == 0:
            wildcard[conference_name][division_name].append(team)
        else:
            wildcard[conference_name]["Wildcard"].append(team)
    return wildcard



def test_standings(standing_type="division"):
    standings = fetch_standings()
    print(standings)
    division_standings = get_division_standings(standings["data"])
    conference_standings = get_conference_standings(standings["data"])
    wildcard_standings = get_wildcard_standings(standings["data"])

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