import requests
import json
from datetime import datetime, timezone
from .domains import BASEWEB


# Known Codes and states used on the API
EVENT_TYPE_CODE = {
    "faceoff": 502,
    "hit": 503,
    "giveaway": 504,
    "goal": 505,
    "shot_on_goal": 506,
    "missed_shot": 507,
    "blocked_shot": 508,
    "penalty": 509,
    "stoppage": 516,
    "period_start": 520,
    "period_end": 521,
    "shootout_complete": 523,
    "game_end": 524,
    "takeaway": 525,
    "delayed_penalty": 535,
    "failed_shot_attempt": 537
}

GAME_STATE_CODE = {
    "future": "FUT",
    "pregame": "PRE",
    "softFinal": "OVER",
    "hardFinal": "FINAL",
    "official": "OFF",
    "live": "LIVE",
    "critical": "CRIT"
}

GAME_SCHEDULE_STATE_CODE = {
    "scheduled": "OK",
    "toBeDetermined": "TBD",
    "postponed": "PPD",
    "suspended": "SUSP",
    "cancelled": "CNCL"
}

GAME_OUTCOME_CODE = {
    "regulation": "REG",
    "overtime": "OT",
    "shootout": "SO"
}

EXEMPLE_DATA = {"default":"game","goal":"game_new_goal_play"}

def fetch(id):
    url = f"{BASEWEB}/gamecenter/{id}/play-by-play"
    data = {}
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception if the response status code is not in the 2xx range (e.g., 200 OK)
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Request to {url} failed: {e}")
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"timestamp":timestamp, "data":data}

def fetch_exemple(type="default"):
    with open(f"nhl_api_redux/endpoint_exemples/{EXEMPLE_DATA[type]}.json", 'r') as file:
        data = json.load(file)
        return data

class Game:
    def __init__(self, gameid, delay=30):
        self.event_type_code = EVENT_TYPE_CODE
        self.game_state_code = GAME_STATE_CODE
        
        self.alerts_prefered_team_only = False
        
        # Added Delay which the data will be updated.This is on top of the time it takes for the API data to refresh which seems to be 15sec (use to be 60sec).
        self.delay = delay 
        self.databuffer = [] # Buffer to save data to delay what is presented and sync with TV broadcast or radio. (Try to prevent spoilers)
        self.gameid = gameid
        
        self.away_team_id = None
        self.away_team_name = None
        self.away_score = 0
        
        self.home_team_id = None
        self.home_team_name = None
        self.home_score = 0

        self.game_state = ""
        self.game_schedule_state = ""
        self.clock = None
        self.is_clock_running = False
        self.in_intermission = False
        self.period = 0
        self.periodDescriptor = {}
        self.period_type = ""
        
        self.situation = {}
        self.in_situation = False
        self.situation_code = ""
        self.situation_time_remaining = ""
        
        self.game_outcome = ""
        
        self.ready = False
    
    def init_game(self):
        # If the game was not initiated, hydrate variables right away. 
        if not self.ready:
            self._refresh_data()
            if self._hydrate(self.databuffer[0]["data"]):
                self.ready = True
        
        return self.ready
        
    def update(self):
        self._refresh_data()
        
        # When initiated, the first data set in the buffer is already consumed by the instance. 
        # So we need to make sure that there is at least 2 entry in order to compare data sets (to find new goals and penalties and others)
        if len(self.databuffer) >= 2:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            
            # We compare the timestamp of the second entry since the fist entry is already consumed.
            data_time_stamp = self.databuffer[1]["timestamp"]
            print(f"\n{data_time_stamp}")
            
            # Until the oldest data set in the buffer is not older then the delay, we wait
            if self._compare_timestamp(now, data_time_stamp) >= self.delay:

                # It is best to keep the data set that match the latest stored variable 
                # so we can easily check for goals and penalties (or other data). 
                # Thats why we remove the first entry before we hydrate (because that entry was already consumed)
                
                self.databuffer.pop(0)
                self._hydrate(self.databuffer[0]["data"])
        return
    
    def _hydrate(self, gamedata):
        if gamedata:
            self.away_team_id = gamedata["awayTeam"]["id"]
            self.away_team_name = gamedata["awayTeam"]["name"]
            self.home_team_id = gamedata["homeTeam"]["id"]
            self.home_team_name = gamedata["homeTeam"]["name"]
            self.away_score = gamedata['awayTeam'].get('score','0')
            self.home_score = gamedata['homeTeam'].get('score','0')
            
            self.game_state = gamedata["gameState"]
            self.game_schedule_state = gamedata["gameScheduleState"]
            self.clock = gamedata["clock"]["timeRemaining"]
            self.is_clock_running = gamedata["clock"]["running"]
            self.in_intermission = gamedata["clock"]["inIntermission"]
                        
            #
            # These are data that appear on the API depending on the Game state or Situation (Powerplays, pulled goalies). 
            # We try to find they are present, if not we replace they with their default data.
            #
            
            self.period = gamedata.get("period", 0)
            self.period_descriptor = gamedata.get("periodDescriptor", {})
            if self.period_descriptor:
                self.period_type = self.period_descriptor.get("periodType", "")
            
            self.situation = gamedata.get("situation",{})
            self.in_situation = True if self.situation else False
            
            if self.in_situation:
                self.situation_code = self.situation.get("situationCode","")
                self.situation_time_remaining = self.situation.get("situationCode","")
            else:
                self.situation_code = ""
                self.situation_time_remaining = ""
                
            self.game_outcome_info = gamedata.get("gameOutcome",{})
            
            if self.game_outcome_info:
                self.game_outcome = self.game_outcome_info.get("lastPeriodType","")
            
            self.plays = gamedata["plays"]
        else:
            return False
        
        return True
        
    def _refresh_data(self):
        data = fetch(self.gameid)
        self.databuffer.append(data)
    
    def _get_player_info(self, playerid, gamedata):
        first_name = ""
        last_name = ""
        number = None
        teamid = None
        
        for player in gamedata["rosterSpots"]:
            if player["playerId"] == playerid:
                first_name = player["firstName"]
                last_name = player["lastName"]
                number = player["sweaterNumber"]
                teamid = player["teamId"]
                return {"playerId":playerid,"teamId":teamid, "firstName":first_name, "lastName":last_name, "sweaterNumber":number}
            
        return {}
        
    def _get_type_plays(self, gamedata, type):
        type_plays = []
        plays = gamedata["plays"]
        for p in plays:
            if p["typeCode"] == self.event_type_code[type]:
                
                play_details = p["details"]
                scoring_player_id = play_details.get("scoringPlayerId", None)
                assist1_player_id = play_details.get("assist1PlayerId", None)
                assist2_player_id = play_details.get("assist2PlayerId", None)
                
                if scoring_player_id:
                    p["details"]["scoringPlayerInfo"] = self._get_player_info(scoring_player_id, gamedata)
                    
                if assist1_player_id:
                    p["details"]["assist1PlayerInfo"] = self._get_player_info(assist1_player_id, gamedata)
                    
                if assist2_player_id:
                    p["details"]["assist2PlayerInfo"] = self._get_player_info(assist2_player_id, gamedata)
                
                type_plays.append(p)
        return type_plays
    
    # This is not required as this should be done on the client side. 
    # We only need to provide the goal plays and let the client do what they want.
    def check_new_goal_plays(self):
        current_goal_ids = []
        new_plays = []
        if self.databuffer >= 2:
            oldgamedata = self.databuffer[0]
            newgamedata = self.databuffer[1]
            
            old_goal_plays = self._get_type_plays(oldgamedata,"goal")
            new_goal_plays = self._get_type_plays(newgamedata,"goal")
            
            if old_goal_plays and new_goal_plays:
                for play in old_goal_plays:
                    current_goal_ids.append(play["eventId"])
                    
                for new_play in new_goal_plays:
                    if new_play["eventId"] not in current_goal_ids:
                        new_plays.append(new_play)
        return new_plays

    def check_new_goal(self, teamid=None):
        if self.databuffer >= 2:
            oldgamedata = self.databuffer[0]
            newgamedata = self.databuffer[1]
            
            if teamid:
                if teamid == newgamedata["homeTeam"]["id"]:
                    old_score = oldgamedata["homeTeam"]["score"]
                    new_score = newgamedata["homeTeam"]["score"]
                    return new_score > old_score
                    
                elif teamid == newgamedata["awayTeam"]["id"]:
                    old_score = oldgamedata["awayTeam"]["score"]
                    new_score = newgamedata["awayTeam"]["score"]
                    return new_score > old_score
                
                print(f"No new goal for {teamid}" )
                return False
            
            else:
                home_old_score = oldgamedata["homeTeam"]["score"]
                home_new_score = newgamedata["homeTeam"]["score"]
                away_old_score = oldgamedata["awayTeam"]["score"]
                away_new_score = newgamedata["awayTeam"]["score"]
                
                return (home_new_score > home_old_score or away_new_score > away_old_score)
        
        return False
    
    def _compare_timestamp(self, ts1, ts2):
        timestamp1 = datetime.strptime(ts1, "%Y-%m-%dT%H:%M:%SZ")
        timestamp2 = datetime.strptime(ts2, "%Y-%m-%dT%H:%M:%SZ")
        time_difference = timestamp1 - timestamp2
        return int(time_difference.total_seconds())