from .domains import BASE
from .seasons import get_current_season
import requests
import json
from datetime import datetime, timezone
"""
    Top 10 Leaders per categories 
        Goal:
            Skaters endpoint: https://api.nhle.com/stats/rest/en/leaders/skaters/goals?cayenneExp=season=20232024%20and%20gameType=2
            Defence endpoint: https://api.nhle.com/stats/rest/en/leaders/skaters/goals?cayenneExp=season=20232024%20and%20gameType=2%20and%20player.positionCode%20=%20%27D%27
            Rookies endpoint: https://api.nhle.com/stats/rest/en/leaders/skaters/goals?cayenneExp=season=20232024%20and%20gameType=2%20and%20isRookie%20=%20%27Y%27
        
        Points:
            Skaters endpoint: https://api.nhle.com/stats/rest/en/leaders/skaters/points?cayenneExp=season=20232024%20and%20gameType=2
            Defence endpoint: https://api.nhle.com/stats/rest/en/leaders/skaters/points?cayenneExp=season=20232024%20and%20gameType=2%20and%20player.positionCode%20=%20%27D%27
            Rookies endpoint: https://api.nhle.com/stats/rest/en/leaders/skaters/points?cayenneExp=season=20232024%20and%20gameType=2%20and%20isRookie%20=%20%27Y%27
            
        Assists:    
            Skaters endpoint: https://api.nhle.com/stats/rest/en/leaders/skaters/assists?cayenneExp=season=20232024%20and%20gameType=2
            Defence endpoint: https://api.nhle.com/stats/rest/en/leaders/skaters/assists?cayenneExp=season=20232024%20and%20gameType=2%20and%20player.positionCode%20=%20%27D%27
            Rookies endpoint: https://api.nhle.com/stats/rest/en/leaders/skaters/assists?cayenneExp=season=20232024%20and%20gameType=2%20and%20isRookie%20=%20%27Y%27
            
        Goalies:            
            Goal against endpoint: https://api.nhle.com/stats/rest/en/leaders/goalies/gaa?cayenneExp=season=20232024%20and%20gameType=2%20and%20gamesPlayed%20%3E=%2020
            Save % endpoint : https://api.nhle.com/stats/rest/en/leaders/goalies/savePctg?cayenneExp=season=20232024%20and%20gameType=2%20and%20gamesPlayed%20%3E=%2020
            Shutouts endpoint: https://api.nhle.com/stats/rest/en/leaders/goalies/shutouts?cayenneExp=season=20232024%20and%20gameType=2%20and%20gamesPlayed%20%3E=%2020
"""     

GAMETYPE = {"regular":2, "postseason":3}

def fetch_leaders(stat_type, category, position=None, rookie=False, season="current", gametype="regular"):
    
    if season == "current":
        season = get_current_season()
    
    base_url = "https://api.nhle.com/stats/rest/en/leaders/"
    endpoint = f"{category}/{stat_type}"
    params = {"cayenneExp": f"season={season} and gameType={GAMETYPE[gametype]}"}

    if position:
        if position not in ["D","C","L","R"]:
            raise ValueError('The position provided is invalid. Must be "D","C","L", or "R"')
        else:
            params["cayenneExp"] += f" and player.positionCode = '{position}'"
    if rookie:
        params["cayenneExp"] += f" and isRookie = 'Y'"

    url = base_url + endpoint
    data = None

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request to {url} failed: {e}")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"timestamp": timestamp, "leaders": data["data"]}

def fetch_leaders_simplified(stat_type, category, position=None, rookie=None, season="current", gametype="regular"):
    raw_leaders = fetch_leaders(stat_type,category,position,rookie,season,gametype)
    print(raw_leaders)
    leaders_simplified = []
    for player_data in raw_leaders["leaders"]:
        player = player_data['player']
        team = player_data['team']
        new_entry = {
            'player_id': player['id'],
            'firstName': player['firstName'],
            'lastName': player['lastName'],
            'positionCode': player['positionCode'],
            'sweaterNumber': player['sweaterNumber'],
            'currentTeamId': player['currentTeamId'],
            'team_fullname': team['fullName'],
            'team_triCode': team['triCode']
        }
        leaders_simplified.append(new_entry)
    return {"timestamp": raw_leaders["timestamp"], "data": leaders_simplified}

