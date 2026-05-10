import json
import re
from pathlib import Path
from psycopg2.extras import execute_batch
from datetime import datetime, timezone

from models import Post, MentionDataPoint
from storage.database_manager import get_existing_post_ids_batch
from analysis.mention_analyser import MentionAnalyser

import logging

logger = logging.getLogger(__name__)

_CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})\b")
_BARE_RE = re.compile(r"\b([A-Za-z]{2,5})\b")

_BLACKLIST_PATH = Path(__file__).parent / "lowercase_ticker_blacklist.json"
with open(_BLACKLIST_PATH) as f:
    _LOWERCASE_TICKER_BLACKLIST: frozenset[str] = frozenset(json.load(f))


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
                ON CONFLICT (post_id) DO UPDATE SET
                    num_comments = GREATEST(posts.num_comments, EXCLUDED.num_comments),
                    score = EXCLUDED.score
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
                ON CONFLICT (post_id) DO UPDATE SET
                    num_comments = GREATEST(posts.num_comments, EXCLUDED.num_comments),
                    score = EXCLUDED.score
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

    def find_tickers_in_text(self, text: str) -> set[str]:
        """Return the set of valid tickers (uppercase) found in `text`.

        Cashtags (`$tsla`) and uppercase bare words (`TSLA`) match unconditionally.
        Lowercase words are filtered through a blacklist of common english words.
        """
        cashtagged = {m.group(1).upper() for m in _CASHTAG_RE.finditer(text)}
        bare_upper: set[str] = set()
        bare_other: set[str] = set()
        for m in _BARE_RE.finditer(text):
            word = m.group(1)
            if word.isupper():
                bare_upper.add(word)
            else:
                bare_other.add(word.upper())
        bare_other -= _LOWERCASE_TICKER_BLACKLIST
        return (cashtagged | bare_upper | bare_other) & self.valid

    def _batch_save_post_mentions(self, rows: list[tuple]) -> None:
        """Persist (post_id, ticker) rows so the rollup can be re-derived later."""
        if not rows or not self.connection_pool:
            return

        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        try:
            execute_batch(
                cursor,
                """
                INSERT INTO post_mentions (post_id, ticker)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error batch saving post_mentions: {e}")
            raise
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)

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
        mention_data = {}  # key: (ticker, subreddit, hour_bucket) -> {...}
        post_mention_rows: list[tuple] = []

        posts_with_mentions = 0
        for post in posts_to_process:
            # Bucket by the post's creation hour UTC
            hour_bucket = datetime.fromtimestamp(
                post.created_utc, tz=timezone.utc
            ).replace(minute=0, second=0, microsecond=0)

            unique_tickers = self.find_tickers_in_text(post.text)
            if unique_tickers:
                posts_with_mentions += 1

            text_upper = post.text.upper()
            text_long_enough = len(post.text.strip()) >= 15

            for t in unique_tickers:
                post_mention_rows.append((post.id, t))
                key = (t, post.subreddit, hour_bucket)
                if key not in mention_data:
                    mention_data[key] = {
                        "count": 0,
                        "users": set(),
                        "total_score": 0,
                        "total_comments": 0,
                        "sentiments": [],
                    }
                mention_data[key]["count"] += 1
                mention_data[key]["users"].add(post.user_id)
                mention_data[key]["total_score"] += post.score
                mention_data[key]["total_comments"] += post.num_comments

                if text_long_enough and t in text_upper:
                    mention_data[key]["sentiments"].append(
                        self.mention_analyser._effective_sentiment(post)
                    )

        logger.info(
            f"Processed {len(posts_to_process)} new posts, found ticker mentions in {posts_with_mentions} posts"
        )

        # Persist the per-post -> ticker map. Allows rebuilding the rollup
        # offline if regex/valid_tickers ever changes.
        if post_mention_rows:
            self._batch_save_post_mentions(post_mention_rows)

        # Convert mention_data dictionary to list of MentionDataPoint objects
        mention_data_points = []
        for (ticker, subreddit, hour_bucket), data in mention_data.items():
            sentiments = data["sentiments"]
            sentiment_sum = sum(sentiments)
            post_count = len(sentiments)
            avg_sentiment = (sentiment_sum / post_count) if post_count else 0.0

            mention_data_points.append(
                MentionDataPoint(
                    ticker=ticker,
                    subreddit=subreddit,
                    timestamp=hour_bucket,
                    mention_count=data["count"],
                    unique_users=len(data["users"]),
                    total_score=data["total_score"],
                    total_comments=data["total_comments"],
                    avg_sentiment=round(avg_sentiment, 4),
                    sentiment_sum=sentiment_sum,
                    post_count=post_count,
                    user_ids=frozenset(data["users"]),
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
