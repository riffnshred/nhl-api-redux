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


def game_schedule_is_irregular(code): 
    return code in [GAME_SCHEDULE_STATE_CODE["postponed"], GAME_SCHEDULE_STATE_CODE["suspended"], GAME_SCHEDULE_STATE_CODE["cancelled"]]

def game_is_scheduled(code):
    return code in [GAME_SCHEDULE_STATE_CODE["scheduled"]]

def game_is_pre_game(code):
    return code in [GAME_STATE_CODE["future"], GAME_STATE_CODE["pregame"]]

def game_is_over(code):
    return code in [GAME_STATE_CODE["softFinal"], GAME_STATE_CODE["hardFinal"], GAME_STATE_CODE["official"]]

def game_is_critical(code):
    return code in [GAME_SCHEDULE_STATE_CODE["critical"]]

def game_is_live(code):
    return code in [GAME_SCHEDULE_STATE_CODE["live"],GAME_SCHEDULE_STATE_CODE["critical"]]