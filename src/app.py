from reddit.RedditClient import RedditClient
from reddit.TickerMentionScanner import TickerMentionScanner
from storage.Database import Database
from dotenv import load_dotenv
import os

load_dotenv()

VALID = ['AAPL', 'TSLA', 'MSFT', 'NVDA']

client_id = os.getenv("REDDIT_CLIENT_ID")
client_secret = os.getenv("REDDIT_CLIENT_SECRET")
user_agent = os.getenv("REDDIT_USER_AGENT")

reddit = RedditClient(client_id, client_secret, user_agent)
scanner = TickerMentionScanner(VALID)
db = Database()

texts = list(reddit.fetch_recent_posts("wallstreetbets", limit=300))
counts = scanner.count_mentions(texts)
db.insert_mention_counts(counts)

print("done. Counts: ", counts)