import requests
import json
from datetime import datetime, timezone
from .domains import BASEWEB, DEFAULT_TIMEOUT
from .logger import logger
from .seasons import get_previous_season_id


# Known Codes and states used on the API
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

# TODELETE WHEN V1.0 is Published
# EXEMPLE_DATA = {"default":"game","goal":"game_new_goal_play"}

def fetch(id):
    """
    Fetch game data from NHL API using the landing endpoint

    Args:
        id: Game ID
    """
    url = f"{BASEWEB}/gamecenter/{id}/landing"

    data = {}
    try:
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()  # Raise an exception if the response status code is not in the 2xx range (e.g., 200 OK)
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.warning("Request to %s failed: %s", url, e)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"timestamp":timestamp, "data":data}

def fetch_exemple(file):
    with open(f"{file}", 'r') as f:
        data = json.load(f)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"timestamp":timestamp, "data":data}

class Game:
    def __init__(self, gameid=0, delay=15, debug=False, debug_game_data_file="game.json"):
        self.id = gameid
        
        if not debug and gameid == 0:
            raise ValueError("No gameid provided. Please provide a gameid.")
        
        self.debug = debug

        self.debug_file = debug_game_data_file

        self.game_state_code = GAME_STATE_CODE
        
        self.alerts_prefered_team_only = False
        
        # Added Delay which the data will be updated.This is on top of the time it takes for the API data to refresh which seems to be 15sec (use to be 60sec).
        self.delay = delay 
        self.databuffer = [] # Buffer to save data to delay what is presented and sync with TV broadcast or radio. (Try to prevent spoilers)
        
        self.is_live = False
        
        self.away_team_id = None
        self.away_team_abbrev = None
        self.away_team_name = None
        self.away_team_city = None
        self.away_score = 0
        self.away_shots_on_goal = 0
        
        self.home_team_id = None
        self.home_team_abbrev = None
        self.home_team_name = None
        self.home_team_city = None
        self.home_score = 0
        self.home_shots_on_goal = 0

        self.game_date = ""
        self.start_time_UTC = ""
        self.game_schedule_state = ""
        
        self.state = ""
        self.clock = None
        self.is_clock_running = False
        self.in_intermission = False
        self.period_number = 0
        self.periodDescriptor = {}
        self.period_type = ""
        
        self.situation = {}
        self.in_situation = False
        self.situation_code = ""
        self.situation_time_remaining = ""
        
        self.game_outcome = ""
        
        self.away_team_record = ""
        self.home_team_record = ""
        
        self.away_team_stats = {}
        self.home_team_stats = {}
        
        self.season_id = ""
        self.team_stats_season_id = None
        
        self.ready = False
    
    def init_game(self):
        # If the game was not initiated, sync variables right away. 
        if not self.ready:
            # First fetch from landing endpoint to get team records
            self._fetch_initial_data()
            if self._sync(self.databuffer[0]["data"]):
                # After hydrating game data, fetch team stats
                self._fetch_team_stats()
                # Build team records from stats
                self._build_team_records()
                self.ready = True
        
        return self.ready
    
    def _build_team_records(self):
        """
        Build team records in W-L-OTL format from team stats
        """
        if self.away_team_stats:
            wins = self.away_team_stats.get('wins', 0)
            losses = self.away_team_stats.get('losses', 0)
            ot_losses = self.away_team_stats.get('otLosses', 0)
            self.away_team_record = f"{wins}-{losses}-{ot_losses}"
        
        if self.home_team_stats:
            wins = self.home_team_stats.get('wins', 0)
            losses = self.home_team_stats.get('losses', 0)
            ot_losses = self.home_team_stats.get('otLosses', 0)
            self.home_team_record = f"{wins}-{losses}-{ot_losses}"
    
    def _fetch_initial_data(self):
        """Fetch initial game data from landing endpoint"""
        if self.debug:
            data = fetch_exemple(self.debug_file)
        else:
            data = fetch(self.id)

        self.databuffer.append(data)
    
    def _fetch_team_stats(self):
        """
        Fetch regular-season stats for both teams using NHL API.

        Before a season's first regular-season game (offseason, preseason) the
        current season has no stats yet, so this falls back to the previous
        season. `team_stats_season_id` records which season the stats are from.
        """
        if not self.season_id or not self.away_team_id or not self.home_team_id:
            logger.warning("Missing season_id or team IDs, cannot fetch team stats")
            return

        try:
            season_id = self.season_id
            teams_data = self._query_team_stats(season_id)
            if not teams_data:
                season_id = get_previous_season_id(self.season_id)
                logger.debug("No %s team stats yet, falling back to %s", self.season_id, season_id)
                teams_data = self._query_team_stats(season_id)

            if not teams_data:
                logger.warning("No team stats data returned from API")
                return

            # Separate stats by team ID
            for team_data in teams_data:
                team_id = team_data.get("teamId")
                if team_id == self.away_team_id:
                    self.away_team_stats = team_data
                elif team_id == self.home_team_id:
                    self.home_team_stats = team_data
            self.team_stats_season_id = season_id

            logger.debug("Fetched %s stats for teams %s and %s", season_id, self.away_team_id, self.home_team_id)

        except requests.exceptions.RequestException as e:
            logger.warning("Failed to fetch team stats: %s", e)

    def _query_team_stats(self, season_id):
        """Return the regular-season stats rows for both teams in `season_id`."""
        url = f"https://api.nhle.com/stats/rest/en/team/summary?cayenneExp=seasonId={season_id}%20and%20gameTypeId=2%20and%20(teamId={self.away_team_id}%20or%20teamId={self.home_team_id})"
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json().get("data", [])
        
    def update(self, auto_sync=True):
        """
        Refresh game data from API and optionally auto-sync when delay threshold is met.

        Args:
            auto_sync (bool): If True, automatically sync state when delay threshold is met.
                             If False, returns time delta for manual scheduling instead.

        Returns:
            int or None: When auto_sync=False, returns seconds until data should be synced
                        if new data changed (None if no change or not enough buffer entries).
                        When auto_sync=True, always returns None.

        Example with auto_sync=True (default):
            game.update()  # Fetches data and auto-syncs when ready

        Example with auto_sync=False (manual scheduling):
            seconds_until_ready = game.update(auto_sync=False)
            if seconds_until_ready is not None:
                # Data changed! Schedule manual_sync() in X seconds
                scheduler.add_job(game.manual_sync, run_date=datetime.now() + timedelta(seconds=seconds_until_ready))
        """
        self._refresh_data()

        # When initiated, the first data set in the buffer is already consumed by the instance.
        # So we need to make sure that there is at least 2 entry in order to compare data sets (to find new goals and penalties and others)
        if len(self.databuffer) < 2:
            return None

        if auto_sync:
            # Auto-sync mode: sync when delay threshold is met
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            # We compare the timestamp of the second entry since the first entry is already consumed.
            data_time_stamp = self.databuffer[1]["timestamp"]
            # Until the oldest data set in the buffer is not older than the delay, we wait
            if self._compare_timestamp(now, data_time_stamp) >= self.delay:
                # It is best to keep the data set that match the latest stored variable
                # so we can easily check for goals and penalties (or other data).
                # Thats why we remove the first entry before we sync (because that entry was already consumed)

                self.databuffer.pop(0)
                self._sync(self.databuffer[0]["data"])
            return None
        else:
            # Manual sync mode: check if data changed and return scheduling delta
            # Compare the last two entries to see if data changed
            latest_data = self.databuffer[-1]["data"]
            previous_data = self.databuffer[-2]["data"]

            # Check if data is different (you can customize this comparison)
            if latest_data == previous_data:
                return None

            # Data changed! Calculate when it should be synced
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            new_data_timestamp = self.databuffer[-1]["timestamp"]

            # Calculate when this data should be ready (timestamp + delay)
            # Return seconds from now until that time
            age_seconds = self._compare_timestamp(now, new_data_timestamp)
            seconds_until_ready = self.delay - age_seconds

            return seconds_until_ready

    def sync_state(self):
        """
        Manually sync with the oldest buffered data, removing it from buffer.
        Use this when your scheduled job triggers based on check_for_update() result.

        Returns:
            bool: True if sync was successful, False if buffer was empty.
        """
        if len(self.databuffer) < 2:
            return False

        # Remove the oldest entry and sync with the next one
        self.databuffer.pop(0)
        return self._sync(self.databuffer[0]["data"])
    
    def _sync(self, gamedata):
        if gamedata:
            self.away_team_id = gamedata["awayTeam"]["id"]
            self.away_team_abbrev = gamedata["awayTeam"]["abbrev"]
            self.away_team_name = gamedata["awayTeam"]["commonName"]["default"]
            self.away_team_city = gamedata["awayTeam"]["placeName"]["default"]
            self.home_team_id = gamedata["homeTeam"]["id"]
            self.home_team_abbrev = gamedata["homeTeam"]["abbrev"]
            self.home_team_name = gamedata["homeTeam"]["commonName"]["default"]
            self.home_team_city = gamedata["homeTeam"]["placeName"]["default"]
            self.away_score = int(gamedata['awayTeam'].get('score','0'))
            self.home_score = int(gamedata['homeTeam'].get('score','0'))    
            self.away_shots_on_goal = int(gamedata['awayTeam'].get('sog','0'))
            self.home_shots_on_goal = int(gamedata['homeTeam'].get('sog','0'))
            self.game_date = gamedata["gameDate"]
            self.start_time_UTC = gamedata["startTimeUTC"]
            self.state = gamedata["gameState"]
            self.game_schedule_state = gamedata["gameScheduleState"]
            
            # Extract season ID if available
            self.season_id = gamedata.get("season", "")
            
            
                        
            #
            # These are data that appear on the API depending on the Game state or Situation (Powerplays, pulled goalies). 
            # We try to find they are present, if not we replace they with their default data.
            #
            
            self.clock = gamedata.get("clock", {})
            self.clock_running = self.clock.get("running", False)
            self.in_intermission = self.clock.get("inIntermission", False)
            self.period_descriptor = gamedata.get("periodDescriptor", {})
            if self.period_descriptor:
                self.period_type = self.period_descriptor.get("periodType", "")
                self.period_number = self.period_descriptor.get("number", 0)
            
            self.situation = gamedata.get("situation",{})
            self.in_situation = True if self.situation else False
            
            if self.in_situation:
                self.situation_code = self.situation.get("situationCode","")
                self.situation_time_remaining = self.situation.get("timeRemaining","")
            else:
                self.situation_code = ""
                self.situation_time_remaining = ""
                
            # Game outcome is not available on landing endpoint
            # Use periodType from periodDescriptor when game is FINAL or OFF
            if self.state in ["FINAL", "OFF"] and self.period_descriptor:
                period_type = self.period_descriptor.get("periodType", "")

                # Map period types to outcomes
                outcome_map = {
                    "REG": "REG",
                    "SO": "SO"
                }

                if period_type in outcome_map:
                    self.game_outcome = outcome_map[period_type]
                elif period_type == "OT":
                    ot_periods = self.period_descriptor.get("otPeriods", 0)
                    self.game_outcome = f"OT{ot_periods}" if ot_periods > 1 else "OT"
                else:
                    self.game_outcome = "FINAL"
            else:
                self.game_outcome = ""

            # Check if the game is live.
            if self.state in ["PRE","LIVE", "CRIT", "OVER"]:
                self.is_live = True
            else:
                self.is_live = False
        else:
            return False
        
        return True
        
    def _refresh_data(self):
        """Refresh game data using landing endpoint"""
        if self.debug:
            data = fetch_exemple(self.debug_file)
        else:
            data = fetch(self.id)

        self.databuffer.append(data)

    def _compare_timestamp(self, ts1, ts2):
        timestamp1 = datetime.strptime(ts1, "%Y-%m-%dT%H:%M:%SZ")
        timestamp2 = datetime.strptime(ts2, "%Y-%m-%dT%H:%M:%SZ")
        time_difference = timestamp1 - timestamp2
        return int(time_difference.total_seconds())
