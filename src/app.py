from reddit.RedditClient import RedditClient
from reddit.TickerMentionScanner import TickerMentionScanner
from storage.Database import Database
from config import CLIENT_ID, CLIENT_SECRET, USER_AGENT

INVALID = ['YOLO', 'HOLD', 'HODL']

reddit = RedditClient(CLIENT_ID, CLIENT_SECRET, USER_AGENT)
scanner = TickerMentionScanner(INVALID)
#db = Database()

texts = list(reddit.fetch_recent_posts("wallstreetbets", limit=300))
counts = scanner.count_mentions(texts)
#db.insert_mention_counts(counts)

print("done. Counts: ", counts)