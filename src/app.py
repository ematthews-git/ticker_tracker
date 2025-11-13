from reddit.RedditClient import RedditClient
from reddit.TickerMentionScanner import TickerMentionScanner
from config import CLIENT_ID, CLIENT_SECRET, USER_AGENT, INVALID, DB_PATH
import schedule
from datetime import datetime
import time
from storage.Database import insert_mention_counts

def collect_data():
    """Collects ticker mentions and saves to database
    """
    print(f"[{datetime.now}] starting data collection...")
    try:
        #initialise clients
        reddit = RedditClient(CLIENT_ID, CLIENT_SECRET, USER_AGENT)
        scanner = TickerMentionScanner(INVALID)

        #fetch posts
        print("Fetching posts from r/pennystocks...")
        posts = list(reddit.fetch_recent_posts("pennystocks", limit=500))
        print(f"Fetched {len(posts)} posts/comments")

        #count mentions and save posts
        print("Counting ticker mentions...")
        counts = scanner.process_mentions(posts)
        print(f"Completed. unique tickers: {len(counts)}")

        #save mentions
        if counts:
            insert_mention_counts(DB_PATH, counts)
            print(f"Saved items to mentions database")
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
    print(f"Started at: {datetime.now}")
    print("Schedule: Every hour")
    print("Press Cmnd+C to stop\n")

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