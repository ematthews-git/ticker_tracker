from reddit.RedditClient import RedditClient
from reddit.TickerMentionScanner import TickerMentionScanner
from storage.Database import Database

print("67")
VALID = ['AAPL', 'TSLA', 'MSFT', 'NVDA']

reddit = RedditClient("REMOVED_CLIENT_ID", "REMOVED_SECRET", "myRedditApp by u/valk3isthebest")
scanner = TickerMentionScanner(VALID)
db = Database()

texts = list(reddit.GetRecentPosts("wallstreetbets", limit=300))
counts = scanner.CountMentions(texts)
db.InsertMentionCounts(counts)

print("done. Counts: ", counts)