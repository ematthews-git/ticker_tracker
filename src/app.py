import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from reddit.RedditClient import RedditClient
from reddit.TickerMentionScanner import TickerMentionScanner
from config import CLIENT_ID, CLIENT_SECRET, USER_AGENT, VALID, DB_URL, SUBREDDITS
import schedule
from datetime import datetime, timezone
import time
from storage.Database import insert_mention_counts
from logging_setup import configure_logging
import logging

def collect_data() -> None:
    """Collects ticker mentions and saves to database
    """
    logger = logging.getLogger(__name__)
    logger.info(f"[{datetime.now(timezone.utc)}] starting data collection...")
    try:
        #initialise clients
        reddit = RedditClient(CLIENT_ID, CLIENT_SECRET, USER_AGENT)
        scanner = TickerMentionScanner(VALID)

        all_posts = []

        #fetch posts from each subreddit
        for subreddit in SUBREDDITS:
            logger.info(f"Fetching posts from r/{subreddit}...")
            posts = list(reddit.fetch_recent_posts(subreddit, limit=200))
            all_posts.extend(posts)
            logger.info(f"Fetched {len(posts)} posts/comments from r/{subreddit}")

        #count mentions and save posts
        logger.info("Counting ticker mentions...")
        mention_data_points = scanner.process_mentions(all_posts)
        logger.info(f"Completed. unique ticker-subreddit combinations: {len(mention_data_points)} \n")

        #save mentions
        if mention_data_points:
            insert_mention_counts(DB_URL, mention_data_points)
            logger.info(f"Saved {len(mention_data_points)} items to mentions database \n {'='*50}")
        else:
            logger.warn("No ticker mentions found")

    except Exception as e:
        logger.error(f"Data collection failed: {e}")

def main():
    """Runs the scheduler every hour at :00
    """
    #get logger
    logger = logging.getLogger(__name__)
    logger.info("Data Collector started")

    print("=" * 50)
    print("Reddit Ticker Mention Collector")
    print("=" * 50)
    logger.info(f"Started at: {datetime.now(timezone.utc)}")
    logger.info("Schedule: Every hour at :00")
    logger.info("Press Ctrl+C to stop\n")
    inp = input("Enter 1 to force data collection now, or anything else to wait for the next hour: ")

    if inp == "1":
        collect_data()

    #schedule the job
    schedule.every().hour.at(":00").do(collect_data)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("\n\n Scheduler stopped by user")

if __name__ == "__main__":
    configure_logging()
    main()