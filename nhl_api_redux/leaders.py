from .domains import BASE
from .seasons import get_current_season
import requests
import json
from datetime import datetime, timezone
from .logger import logger

r"""
    ______ _____  ___ ______  ___  ___ _____                     
    | ___ \  ___|/ _ \|  _  \ |  \/  ||  ___|                    
    | |_/ / |__ / /_\ \ | | | | .  . || |__                      
    |    /|  __||  _  | | | | | |\/| ||  __|                     
    | |\ \| |___| | | | |/ /  | |  | || |___                     
    \_| \_\____/\_| |_/___/   \_|  |_/\____/                     
                                                                
                                                                
    ______ ___________ ___________ _____                         
    | ___ \  ___|  ___|  _  | ___ \  ___|                        
    | |_/ / |__ | |_  | | | | |_/ / |__                          
    | ___ \  __||  _| | | | |    /|  __|                         
    | |_/ / |___| |   \ \_/ / |\ \| |___                         
    \____/\____/\_|    \___/\_| \_\____/                         
                                                                
                                                                
    _____ _____ _   _ _____ _____ _   _ _   _ _____ _   _ _____ 
    /  __ \  _  | \ | |_   _|_   _| \ | | | | |_   _| \ | |  __ \
    | /  \/ | | |  \| | | |   | | |  \| | | | | | | |  \| | |  \/
    | |   | | | | . ` | | |   | | | . ` | | | | | | | . ` | | __ 
    | \__/\ \_/ / |\  | | |  _| |_| |\  | |_| |_| |_| |\  | |_\ \
    \____/\___/\_| \_/ \_/  \___/\_| \_/\___/ \___/\_| \_/\____/
                                                                
                                                           

    NOTE:

    REPLACE THE api.nhle.com ENDPOINTS FOR THE skater-stats-leaders . details here:
    https://github.com/Zmalski/NHL-API-Reference?tab=readme-ov-file#skaters
    
    Get skaters leader for assist, goals, points in a single endpoint
    https://api-web.nhle.com/v1/skater-stats-leaders/20232024/2?categories=goals,assists,points&limit=5
"""



GAMETYPE = {"regular":2, "postseason":3}

def fetch_leaders(stat_type, category, position=None, rookie=False, season="current", gametype="regular"):
    
    if season == "current":
        season = get_current_season()
    
    base_url = "https://api.nhle.com/stats/rest/en/leaders/"
    endpoint = f"{category}/{stat_type}"
    cayenneExp = f"season={season}%20and%20gameType={GAMETYPE[gametype]}"

    if position:
        if position not in ["D","C","L","R"]:
            raise ValueError('The position provided is invalid. Must be "D","C","L", or "R"')
        else:
            cayenneExp += f"%20and%20player.positionCode='{position}'"
    if rookie:
        cayenneExp += f"%20and%20isRookie='Y'"

    url = base_url + endpoint + "?cayenneExp=" + cayenneExp
    data = None

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.warning("Request to %s failed: %s", url, e)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"timestamp": timestamp, "leaders": data["data"]}




def tailored_leaders(stat_type, category, position=None, rookie=None, season="current", gametype="regular"):
    raw_leaders = fetch_leaders(stat_type,category,position,rookie,season,gametype)
    leaders_simplified = []
    for player_data in raw_leaders["leaders"]:
        player = player_data['player']
        team = player_data['team']
        new_entry = {
            f'{stat_type}':  player_data[f'{stat_type}'],
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

