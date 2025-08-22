##data/apikey_data.py
import json
import os

APIKEY_FILE = "data/user_apikeys.json"

def load_apikeys():
    if not os.path.exists(APIKEY_FILE):
        return {}
    with open(APIKEY_FILE, "r") as f:
        return json.load(f)

def save_apikeys(data):
    with open(APIKEY_FILE, "w") as f:
        json.dump(data, f, indent=4)
