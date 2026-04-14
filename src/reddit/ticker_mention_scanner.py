import re
import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime, timezone

from models import Post, MentionDataPoint
from storage.database_manager import get_existing_post_ids_batch
from analysis.mention_analyser import MentionAnalyser

import logging

logger = logging.getLogger(__name__)


class TickerMentionScanner:
    """Scans for Ticker Mentions and saves posts to database."""

    def __init__(self, valid_tickers, connection_pool=None):
        """
        Args:
            valid_tickers: List of ticker symbols to search for
            connection_pool: The PostgreSQL connection pool (optional)
        """
        self.valid = set(valid_tickers)
        self.connection_pool = connection_pool
        self.mention_analyser = MentionAnalyser()

    def save_post(self, post: Post) -> None:
        """Saves one post to the posts table of database.

        Args:
            post (Post): An instance of the Post dataclass.
        """
        if not self.connection_pool:
            raise ValueError("Connection pool is required to save posts")

        conn = self.connection_pool.getconn()
        cursor = conn.cursor()

        try:
            # Convert Unix timestamp to datetime (UTC)
            created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            cursor.execute(
                """
                INSERT INTO posts (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
                """,
                (
                    post.id,
                    post.subreddit,
                    created_dt,
                    post.text,
                    post.link_flair_text,
                    post.type,
                    post.origin_id,
                    post.user_id,
                    post.score,
                    post.upvote_ratio,
                    post.num_comments,
                    post.author_quality,
                ),
            )

            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving post {post.id}: {e}")
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)

    def _batch_save_posts(self, posts_data: list[tuple]) -> None:
        """Batch saves multiple posts to the database in a single transaction.

        Args:
            posts_data: List of tuples (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
        """
        if not posts_data:
            return

        if not self.connection_pool:
            raise ValueError("Connection pool is required to save posts")

        conn = self.connection_pool.getconn()
        cursor = conn.cursor()

        try:
            execute_batch(
                cursor,
                """
                INSERT INTO posts (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
                """,
                posts_data,
            )

            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error batch saving posts: {e}")
            raise
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)

    def _find_new_posts(self, post_list: list[Post]) -> list[Post]:
        """Takes a list of posts and finds all posts not already saved in the database.

        Args:
            post_list (list[Post]): Posts to search for new posts within.

        Returns:
            list[Post]: All posts from the passed list which are not yet in the database.
        """
        post_ids_to_check = [p.id for p in post_list]
        existing_ids = set()

        if self.connection_pool and post_ids_to_check:
            existing_ids = get_existing_post_ids_batch(
                self.connection_pool, post_ids_to_check
            )

        logger.info(
            f"Found {len(existing_ids)} existing posts in batch of {len(post_ids_to_check)}"
        )

        # Collect new posts to batch insert
        new_posts = []

        for post in post_list:
            # skip if already processed
            if post.id in existing_ids:
                continue

            new_posts.append(post)

        return new_posts

    def _posts_to_tuples(self, post_list: list[Post]) -> list[tuple]:
        """Simple convert a list of Post objects to a list of tuples.

        Args:
            post_list (Post): A list of Posts.

        Returns:
            list[tuple]: A list of equivalent tuples.
                (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
        """
        if not post_list:
            return []

        tuples = []
        for post in post_list:
            created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            tuples.append(
                (
                    post.id,
                    post.subreddit,
                    created_dt,
                    post.text,
                    post.link_flair_text,
                    post.type,
                    post.origin_id,
                    post.user_id,
                    post.score,
                    post.upvote_ratio,
                    post.num_comments,
                    post.author_quality,
                )
            )

        return tuples

    # Counts mentions of valid tickers into list of MentionDataPoint objects
    def process_mentions(self, post_list: list[Post]) -> list[MentionDataPoint]:
        """finds the mention of any valid ticker in the list of text parsed and saves each post to db.

        Args:
            post_list (Iterable[Post]): The list of post items to search.

        Returns:
            list[MentionDataPoint]: A list of MentionDataPoint objects representing ticker mentions.
        """
        # Only process new posts - if a post already exists, it was already counted
        posts_to_process = self._find_new_posts(post_list)
        new_posts = self._posts_to_tuples(posts_to_process)

        # Batch insert all new posts at once
        if new_posts:
            self._batch_save_posts(new_posts)
            logger.info(f"{len(new_posts)} New posts saved to database")
        else:
            logger.info(
                f"No new posts to save (all {len(post_list)} posts already exist in database)"
            )

        # Process ticker mentions for new posts only
        # Track detailed metrics per ticker-subreddit-hour combination
        mention_data = {}  # key: (ticker, subreddit, hour_bucket) -> {count, users, total_score, total_comments}

        posts_with_mentions = 0
        for post in posts_to_process:
            # Bucket by the post's actual creation hour, not the scanner's run time
            hour_bucket = datetime.fromtimestamp(post.created_utc, tz=timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )
            # find ticker mentions
            tickers = re.findall(
                r"\b[A-Z]{2,5}\b", post.text
            )  # captal letters + 2 to 5 characters
            post_has_mention = False
            for t in tickers:
                if t in self.valid:
                    post_has_mention = True
                    key = (t.upper(), post.subreddit, hour_bucket)
                    if key not in mention_data:
                        mention_data[key] = {
                            "count": 0,
                            "users": set(),
                            "total_score": 0,
                            "total_comments": 0,
                            "posts": [],
                        }
                    mention_data[key]["count"] += 1
                    mention_data[key]["users"].add(post.user_id)
                    mention_data[key]["total_score"] += post.score
                    mention_data[key]["total_comments"] += post.num_comments
                    mention_data[key]["posts"].append(post)

            if post_has_mention:
                posts_with_mentions += 1

        logger.info(
            f"Processed {len(posts_to_process)} new posts, found ticker mentions in {posts_with_mentions} posts"
        )

        # Convert mention_data dictionary to list of MentionDataPoint objects
        mention_data_points = []
        for (ticker, subreddit, hour_bucket), data in mention_data.items():
            sentiment = self.mention_analyser.analyse_ticker_sentiment(
                data["posts"], ticker
            )
            avg_sentiment = sentiment["avg_sentiment"]

            mention_data_points.append(
                MentionDataPoint(
                    ticker=ticker,
                    subreddit=subreddit,
                    timestamp=hour_bucket,
                    mention_count=data["count"],
                    unique_users=len(data["users"]),
                    total_score=data["total_score"],
                    total_comments=data["total_comments"],
                    avg_sentiment=avg_sentiment,
                )
            )
        return mention_data_points

    def _get_existing_posts_ids(self) -> set:
        """Gets set of all post IDs already in the database

        Returns:
            set: all post IDs
        """
        if not self.connection_pool:
            raise ValueError("Connection pool is required to get existing posts")

        conn = self.connection_pool.getconn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT post_id FROM posts")
            existing_ids = {row[0] for row in cursor.fetchall()}
            return existing_ids
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
