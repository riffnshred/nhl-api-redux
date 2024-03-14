import datetime
from .domains import BASE
import requests
import json
from datetime import datetime, timezone, date


def fetch_server_status():
    url = f"{BASE}/stats/rest/ping"
    data = None
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception if the response status code is not in the 2xx range (e.g., 200 OK)
        data = response.json()

    except requests.exceptions.RequestException as e:
        print(f"Request to {url} failed: {e}")
        
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")    
    return {"timestamp":timestamp, "data":data}
