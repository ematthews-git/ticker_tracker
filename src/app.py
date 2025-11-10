from reddit.RedditClient import RedditClient
from reddit.TickerMentionScanner import TickerMentionScanner
from storage.Database import Database

print("67")
VALID = ['AAPL', 'TSLA', 'MSFT', 'NVDA']

reddit = RedditClient("A4H9MeTjy52k5sdpvA7-rg", "F_QaKFJRnO5WQK9QSnTb0aG_hVHNwg", "myRedditApp by u/valk3isthebest")
scanner = TickerMentionScanner(VALID)
db = Database()

texts = list(reddit.GetRecentPosts("wallstreetbets", limit=300))
counts = scanner.CountMentions(texts)
db.InsertMentionCounts(counts)

print("done. Counts: ", counts)