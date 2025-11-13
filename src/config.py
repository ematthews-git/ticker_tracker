from dotenv import load_dotenv
import os

load_dotenv()

INVALID = ['YOLO', 'HOLD', 'HODL', 'WSB', 'CEO', 'CFO', 'IPO', 'ETF']
SUBREDDITS = ["pennystocks", "10xpennystocks", "Daytrading", "SmallStreetBets"]

CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
USER_AGENT = os.getenv("REDDIT_USER_AGENT")

DB_PATH = os.getenv("DATABASE_PATH")
