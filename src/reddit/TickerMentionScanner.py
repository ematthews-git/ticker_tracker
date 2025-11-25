import re
import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path to import config and models
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Post, MentionDataPoint

import logging
logger = logging.getLogger(__name__)

class TickerMentionScanner:
    """Scans for Ticker Mentions and saves posts to database.
    """
    def __init__(self, valid_tickers, connection_pool=None):
        """
        Args:
            valid_tickers: List of ticker symbols to search for
            connection_pool: The PostgreSQL connection pool (optional)
        """
        self.valid = set(valid_tickers)
        self.connection_pool = connection_pool

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
            cursor.execute("""
                INSERT INTO posts (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
                """, (post.id, post.subreddit, created_dt, post.text, post.link_flair_text, post.type, post.origin_id, post.user_id, 
                      post.score, post.upvote_ratio, post.num_comments, post.author_quality))
        
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
            execute_batch(cursor, """
                INSERT INTO posts (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
                """, posts_data)
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error batch saving posts: {e}")
            raise
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
    
    #Counts mentions of valid tickers into list of MentionDataPoint objects
    def process_mentions(self, post_list: list[Post]) -> list[MentionDataPoint]:
        """finds the mention of any valid ticker in the list of text parsed and saves each post to db.

        Args:
            post_list (Iterable[Post]): The list of post items to search.

        Returns:
            list[MentionDataPoint]: A list of MentionDataPoint objects representing ticker mentions.
        """
        counts = {}
        timestamp = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        #get existing posts to avoid double counting
        existing_ids = set()
        existing_ids = self._get_existing_posts_ids()
        logger.info(f"Found {len(existing_ids)} existing posts in database")

        # Collect new posts to batch insert
        new_posts = []
        posts_to_process = []

        for post in post_list:
            #skip if already processed
            if post.id in existing_ids:
                continue

            # Convert Unix timestamp to datetime for batch insert (UTC)
            created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            new_posts.append((post.id, post.subreddit, created_dt, post.text, post.link_flair_text, post.type, post.origin_id, post.user_id,
                             post.score, post.upvote_ratio, post.num_comments, post.author_quality))
            posts_to_process.append(post)

        # Batch insert all new posts at once
        if new_posts:
            self._batch_save_posts(new_posts)
            logger.info(f"{len(new_posts)} New posts saved to database")

        # Process ticker mentions for new posts
        # Track detailed metrics per ticker-subreddit combination
        mention_data = {}  # key: (ticker, subreddit) -> {count, users, total_score, total_comments}
        
        for post in posts_to_process:
            #find ticker mentions
            tickers = re.findall(r'\b[A-Z]{2,5}\b', post.text) #captal letters + 2 to 5 characters
            for t in tickers:
                if t in self.valid:
                    key = (t.upper(), post.subreddit)
                    if key not in mention_data:
                        mention_data[key] = {
                            'count': 0,
                            'users': set(),
                            'total_score': 0,
                            'total_comments': 0
                        }
                    mention_data[key]['count'] += 1
                    mention_data[key]['users'].add(post.user_id)
                    mention_data[key]['total_score'] += post.score
                    mention_data[key]['total_comments'] += post.num_comments
            
        logger.info(f"{len(posts_to_process)} New posts processed")
        
        # Convert mention_data dictionary to list of MentionDataPoint objects
        mention_data_points = [
            MentionDataPoint(
                ticker=ticker,
                subreddit=subreddit,
                timestamp=timestamp,
                mention_count=data['count'],
                unique_users=len(data['users']),
                total_score=data['total_score'],
                total_comments=data['total_comments'],
                avg_sentiment=0.0  # Placeholder - sentiment analysis not yet implemented
            )
            for (ticker, subreddit), data in mention_data.items()
        ]
        
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