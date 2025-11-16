import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from reddit.RedditClient import RedditClient
from reddit.TickerMentionScanner import TickerMentionScanner
from config import CLIENT_ID, CLIENT_SECRET, USER_AGENT, INVALID, DB_PATH, SUBREDDITS
import schedule
from datetime import datetime
import time
from storage.Database import insert_mention_counts

def collect_data():
    """Collects ticker mentions and saves to database
    """
    print(f"[{datetime.now()}] starting data collection...")
    try:
        #initialise clients
        reddit = RedditClient(CLIENT_ID, CLIENT_SECRET, USER_AGENT)
        scanner = TickerMentionScanner(INVALID)

        all_posts = []

        #fetch posts from each subreddit
        for subreddit in SUBREDDITS:
            print(f"Fetching posts from r/{subreddit}...")
            posts = list(reddit.fetch_recent_posts(subreddit, limit=200))
            all_posts.extend(posts)
            print(f"Fetched {len(posts)} posts/comments from r/{subreddit}")

        #count mentions and save posts
        print("Counting ticker mentions...")
        mention_data_points = scanner.process_mentions(all_posts)
        print(f"Completed. unique ticker-subreddit combinations: {len(mention_data_points)} \n")

        #save mentions
        if mention_data_points:
            insert_mention_counts(DB_PATH, mention_data_points)
            print(f"Saved {len(mention_data_points)} items to mentions database \n {'='*50}")
        else:
            print("No ticker mentions found")

    except Exception as e:
        print(f"[ERROR] Data collection failed: {e}")

def main():
    """Runs the scheduler every hour at :00
    """
    print("=" * 50)
    print("Reddit Ticker Mention Collector")
    print("=" * 50)
    print(f"Started at: {datetime.now()}")
    print("Schedule: Every hour")
    print("Press Ctrl+C to stop\n")

    #schedule the job
    schedule.every().hour.at(":00").do(collect_data)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n\n Scheduler stopped by user")

if __name__ == "__main__":
    main()