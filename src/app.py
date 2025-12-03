from logging_setup import configure_logging
import logging
configure_logging()

from reddit.reddit_client import RedditClient
from reddit.ticker_mention_scanner import TickerMentionScanner
from config import CLIENT_ID, CLIENT_SECRET, USER_AGENT, VALID, DB_URL, SUBREDDITS
import schedule
from datetime import datetime, timezone
import time
from storage.database_manager import insert_mention_counts
from psycopg2.pool import SimpleConnectionPool

pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,   
    dsn=DB_URL
)

def collect_data() -> None:
    """Collects ticker mentions and saves to database
    """
    logger = logging.getLogger(__name__)
    logger.info(f"[{datetime.now(timezone.utc)}] starting data collection...")
    try:
        #initialise clients
        # RedditClient is not thread safe, so we instantiate it inside the thread
        scanner = TickerMentionScanner(VALID, pool)

        all_posts = []

        # Function to process a single subreddit
        def process_subreddit(subreddit):
            try:
                # Create a new RedditClient instance for this thread
                local_reddit = RedditClient(CLIENT_ID, CLIENT_SECRET, USER_AGENT, pool)
                logger.info(f"Fetching posts from r/{subreddit}...")
                posts = list(local_reddit.fetch_recent_posts(subreddit, limit=200))
                logger.info(f"Fetched {len(posts)} posts/comments from r/{subreddit}")
                return posts
            except Exception as e:
                logger.error(f"Error processing r/{subreddit}: {e}")
                return []

        #fetch posts from each subreddit in parallel
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_sub = {executor.submit(process_subreddit, sub): sub for sub in SUBREDDITS}
            for future in concurrent.futures.as_completed(future_to_sub):
                sub = future_to_sub[future]
                try:
                    posts = future.result()
                    all_posts.extend(posts)
                except Exception as e:
                    logger.error(f"Exception processing r/{sub}: {e}")

        #count mentions and save posts
        logger.info("Counting ticker mentions...")
        mention_data_points = scanner.process_mentions(all_posts)
        logger.info(f"Completed. unique ticker-subreddit combinations: {len(mention_data_points)} \n")

        #save mentions
        if mention_data_points:
            insert_mention_counts(pool, mention_data_points)
            logger.info(f"Saved {len(mention_data_points)} items to mentions database \n {'='*50}")
        else:
            logger.warning("No ticker mentions found")

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
     main()