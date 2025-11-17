from dotenv import load_dotenv
import os
import json

load_dotenv()

def load_valid_tickers():
    """Load valid tickers from JSON"""
    try:
        with open('valid_tickers.json', 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        print("[WARNING] valid_tickers.json not found")
        return set()

VALID = load_valid_tickers()

INVALID = ['YOLO', 'HOLD', 'HODL', 'WSB', 'CEO', 'CFO', 'IPO', 'ETF']
SUBREDDITS = ["pennystocks", "10xpennystocks", "Daytrading", "SmallStreetBets"]

CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
USER_AGENT = os.getenv("REDDIT_USER_AGENT")

DB_PATH = os.getenv("DATABASE_PATH")
DB_URL = os.getenv("DATABASE_URL")
