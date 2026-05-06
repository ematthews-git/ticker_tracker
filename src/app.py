import gc

from reddit.reddit_client import RedditClient
from reddit.ticker_mention_scanner import TickerMentionScanner
from config import (
    CLIENT_ID,
    CLIENT_SECRET,
    USER_AGENT,
    VALID,
    DB_URL,
    SUBREDDITS,
    COMMENT_LOOKBACK_HOURS,
    COMMENT_POSTS_LIMIT,
    STREAM_COMMENT_LIMITS,
    DEFAULT_STREAM_COMMENT_LIMIT,
)
import schedule
from datetime import datetime, timezone
import time
from storage.database_manager import insert_mention_counts, fetch_recent_post_ids
from storage.database_manager import get_existing_post_ids_batch
from psycopg2.pool import SimpleConnectionPool
from utils.collection_stats import append_stat

from logging_setup import configure_logging
import logging

configure_logging()


pool = SimpleConnectionPool(minconn=1, maxconn=3, dsn=DB_URL)


def collect_data() -> None:
    """Collects ticker mentions and saves to database"""
    logger = logging.getLogger(__name__)
    logger.info(f"[{datetime.now(timezone.utc)}] starting data collection...")

    try:
        scanner = TickerMentionScanner(VALID, pool)
        subreddit_stats = {}
        total_mention_data_points = 0
        total_mentions = 0
        total_unique_posts = 0

        for subreddit in SUBREDDITS:
            try:
                reddit = RedditClient(CLIENT_ID, CLIENT_SECRET, USER_AGENT, pool)
                logger.info(f"Fetching posts from r/{subreddit}...")
                stream_limit = STREAM_COMMENT_LIMITS.get(
                    subreddit, DEFAULT_STREAM_COMMENT_LIMIT
                )
                posts, stream_comments, per_post_comments = (
                    reddit.fetch_recent_posts(
                        subreddit, limit=200, stream_comment_limit=stream_limit
                    )
                )
                logger.info(
                    f"r/{subreddit}: {len(posts)} posts, "
                    f"{len(stream_comments)} stream comments, "
                    f"{len(per_post_comments)} per-post comments"
                )

                all_ids = [p.id for p in stream_comments + per_post_comments]
                existing = (
                    get_existing_post_ids_batch(pool, all_ids) if all_ids else set()
                )
                stream_ids = {c.id for c in stream_comments}
                new_stream = sum(1 for c in stream_comments if c.id not in existing)
                new_per_post = sum(
                    1
                    for c in per_post_comments
                    if c.id not in existing and c.id not in stream_ids
                )
                subreddit_stats[subreddit] = {
                    "stream_comments_fetched": len(stream_comments),
                    "per_post_comments_fetched": len(per_post_comments),
                    "new_stream_comments": new_stream,
                    "new_per_post_comments": new_per_post,
                }

                # Deduplicate by post ID as a comment can appear in both the
                # subreddit stream and the per-post comment fetch.
                seen_ids: set[str] = set()
                unique_posts = []
                for p in posts + stream_comments + per_post_comments:
                    if p.id not in seen_ids:
                        seen_ids.add(p.id)
                        unique_posts.append(p)

                total_unique_posts += len(unique_posts)

                mention_data_points = scanner.process_mentions(unique_posts)
                if mention_data_points:
                    insert_mention_counts(pool, mention_data_points)
                    mdp_mentions = sum(
                        mdp.mention_count for mdp in mention_data_points
                    )
                    total_mention_data_points += len(mention_data_points)
                    total_mentions += mdp_mentions

            except Exception as e:
                logger.error(
                    f"SUBREDDIT_FETCH_FAILED sub={subreddit} err={type(e).__name__}: {e}",
                    exc_info=True,
                )
                subreddit_stats[subreddit] = {
                    "error_type": type(e).__name__,
                    "error": repr(e),
                }
            finally:
                gc.collect()

        if total_mention_data_points:
            logger.info(
                f"Completed. Processed {total_unique_posts} posts/comments, "
                f"saved {total_mention_data_points} mention records "
                f"({total_mentions} total mentions) to database \n {'=' * 50}"
            )
        else:
            logger.warning("No ticker mentions found")

        append_stat(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_type": "full_collection",
                "subreddits": subreddit_stats,
            }
        )

    except Exception as e:
        logger.error(f"Data collection failed: {e}")


def collect_older_comments() -> None:
    """Re-fetches comments on recently-active posts to capture ongoing discussion."""
    logger = logging.getLogger(__name__)
    logger.info(f"[{datetime.now(timezone.utc)}] collecting older comments...")
    try:
        post_ids = fetch_recent_post_ids(
            pool, COMMENT_LOOKBACK_HOURS, COMMENT_POSTS_LIMIT
        )
        if not post_ids:
            logger.info("No recent posts found for comment collection")
            return

        reddit = RedditClient(CLIENT_ID, CLIENT_SECRET, USER_AGENT, pool)
        scanner = TickerMentionScanner(VALID, pool)

        comments = reddit.fetch_comments_for_posts(post_ids)
        logger.info(
            f"Fetched {len(comments)} comments from {len(post_ids)} recent posts"
        )

        # Count how many are new before processing
        comment_ids = [c.id for c in comments]
        existing = (
            get_existing_post_ids_batch(pool, comment_ids) if comment_ids else set()
        )
        new_count = sum(1 for c in comments if c.id not in existing)

        mention_data_points = scanner.process_mentions(comments)
        if mention_data_points:
            insert_mention_counts(pool, mention_data_points)
            logger.info(
                f"Saved {len(mention_data_points)} mention records from older comments \n {'=' * 50}"
            )

        append_stat(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_type": "older_comments",
                "posts_checked": len(post_ids),
                "comments_fetched": len(comments),
                "new_comments": new_count,
            }
        )

    except Exception as e:
        logger.error(f"Older comment collection failed: {e}")


def main():
    """Runs the scheduler every hour at :00"""
    # get logger
    logger = logging.getLogger(__name__)
    logger.info("Data Collector started")

    print("=" * 50)
    print("Reddit Ticker Mention Collector")
    print("=" * 50)
    logger.info(f"Started at: {datetime.now(timezone.utc)}")
    logger.info("Schedule: Full collection at :00, older comments at :30")
    logger.info("Press Ctrl+C to stop\n")
    inp = input(
        "Enter 1 to force data collection now, or anything else to wait for the next hour: "
    )

    if inp == "1":
        collect_data()

    # schedule the jobs
    schedule.every().hour.at(":00").do(collect_data)
    schedule.every().hour.at(":30").do(collect_older_comments)

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("\n\n Scheduler stopped by user")


if __name__ == "__main__":
    main()
