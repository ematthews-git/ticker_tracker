from dotenv import load_dotenv
import os
import json
from pathlib import Path

load_dotenv()


def load_valid_tickers():
    """Load valid tickers from JSON"""
    tickers_path = Path(__file__).parent / "valid_tickers.json"
    try:
        with open(tickers_path, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        print(f"[WARNING] valid_tickers.json not found at {tickers_path}")
        return set()


VALID = load_valid_tickers()

_default_log = str(Path.home() / ".ticker_tracker" / "logs" / "reddit-tracker.log")
LOG_PATH = os.getenv("LOG_FILE_PATH", _default_log)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# The subreddits being processed
SUBREDDITS = [
    "pennystocks",
    "10xpennystocks",
    "Daytrading",
    "SmallStreetBets",
    "Shortsqueeze",
    "wallstreetbets",
]

CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
USER_AGENT = os.getenv("REDDIT_USER_AGENT")

DB_PATH = os.getenv("DATABASE_PATH")
DB_URL = os.getenv("DATABASE_URL")
