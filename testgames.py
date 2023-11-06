from nhl_api_redux.games import Game
import time 

g = Game(2023020191)
print(f"Game Initiated: {g.init_game()}")

while True:
    g.update()
    print(f"{g.away_team_name} {g.away_score} vs {g.home_score} {g.home_team_name} \nState: {g.game_state} - {g.period} - {g.clock} \nRunning: {g.is_clock_running}")
    time.sleep(10)
    