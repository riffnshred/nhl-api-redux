import requests
import json
from datetime import datetime, timezone
from .domains import BASEWEB

EMPTY_SCHEDULE = {
   "prevDate":"2023-06-13",
   "currentDate":"2023-08-18",
   "nextDate":"2023-09-23",
   "gameWeek":[
      {
         "date":"2023-08-15",
         "dayAbbrev":"TUE",
         "numberOfGames":0
      },
      {
         "date":"2023-08-16",
         "dayAbbrev":"WED",
         "numberOfGames":0
      },
      {
         "date":"2023-08-17",
         "dayAbbrev":"THU",
         "numberOfGames":0
      },
      {
         "date":"2023-08-18",
         "dayAbbrev":"FRI",
         "numberOfGames":0
      },
      {
         "date":"2023-08-19",
         "dayAbbrev":"SAT",
         "numberOfGames":0
      },
      {
         "date":"2023-08-20",
         "dayAbbrev":"SUN",
         "numberOfGames":0
      },
      {
         "date":"2023-08-21",
         "dayAbbrev":"MON",
         "numberOfGames":0
      }
   ],
   "games":[
      
   ]
}

def get_current_date():
    current_date = datetime.now()
    return current_date.strftime("%Y-%m-%d")

# Get the schedule off the API. If a data is provided it need to be
def fetch_schedule(date=None):
    try:
        if date:
            datetime.strptime(date, "%Y-%m-%d")
        else:
            date = get_current_date()
    except ValueError:
        raise ValueError("Error - Schedule - Fetch - Wrong date format provided, must be YYYY-MM-DD")
        return {}
    
    date_url = f"{BASEWEB}/score/{date}"
    response = requests.get(date_url)
    response.raise_for_status()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"timestamp":timestamp, "data":response.json()}

def fetch_empty_schedule():
    return EMPTY_SCHEDULE

def fetch_schedule_exemple():
    with open("nhl_api_redux/endpoint_exemple/schedule_exemple.json", 'r') as file:
        data = json.load(file)
        return data

def tailored_schedule(date=None):
    raw_schedule = fetch_schedule(date)
    games = []
    raw_schedule = raw_schedule.get("data", {})
    currentDate = raw_schedule.get("currentDate")
    
    for game in raw_schedule.get("games", []):
        goals = [
            {
                "period": goal["period"],
                "timeInPeriod": goal["timeInPeriod"],
                "playerId": goal["playerId"],
                "name": goal["name"],
                "assists": [
                    {
                        "playerId": assist["playerId"],
                        "name": assist["name"]["default"], 
                        "assistsToDate": assist["assistsToDate"]
                    } 
                    for assist in goal.get("assists", [])
                ]
            } 
            for goal in game.get("goals", [])
        ]
        
        away_team = game.get("awayTeam", {})
        home_team = game.get("homeTeam", {})
        
        g = {
            "id": game.get("id"),
            "season": game.get("season"),
            "awayTeam": {
                "id": away_team.get("id"),
                "abbrev": away_team.get("abbrev"),
                "name": away_team["name"].get("default"),
                "sog": away_team.get("sog"),
                "score": away_team.get("score"),
            },
            "homeTeam": {
                "id": home_team.get("id"),
                "abbrev": home_team.get("abbrev"),
                "name": home_team["name"].get("default"),
                "sog": home_team.get("sog"),
                "score": home_team.get("score"),
            },
            "gameType": game.get("gameType", ""),
            "startTimeUTC": game.get("startTimeUTC", ""),
            "gameScheduleState": game.get("gameScheduleState", ""),
            "gameState": game.get("gameState", ""),
            "clock": game.get("clock", ""),
            "period": game.get("period", ""),
            "periodDescriptor": game.get("periodDescriptor", {}),
            "goals": goals
        }
        games.append(g)
        
    return {"timestamp": raw_schedule.get("timestamp"), "currentDate": currentDate, "data": games}

def refresh_schedule(date=None):
    s = fetch_simplified(date)
    return s["data"]

    
def test(date=None, teamid=9):
    try:
        scheduled_games = refresh_schedule(date)
        
        fav_team_scheduled = team_scheduled(scheduled_games,teamid)
        if fav_team_scheduled:
            print(f"My Favorite team is scheduled to play today - game id {fav_team_scheduled}")
        else:
            print(f"My Favorite team is Off today")
            
        for game in scheduled_games:
            away_team_abbrev = game["awayTeam"]["abbrev"]
            home_team_abbrev = game["homeTeam"]["abbrev"]
            game_state = game["gameState"]
            
            print(f"{away_team_abbrev} {game['awayTeam'].get('score','')} VS {game['homeTeam'].get('score','')} {home_team_abbrev} - State: {game_state}" )
            
    except Exception as e:
        print(f"Schedule Test failed! Error: {e}")
        return False

    return True




