import re
import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path to import config and models
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_URL
from models import Post, MentionDataPoint

import logging
logger = logging.getLogger(__name__)

class TickerMentionScanner:
    """Scans for Ticker Mentions and saves posts to database.
    """
    def __init__(self, valid_tickers):
        """
        Args:
            valid_tickers: List of ticker symbols to search for
        """
        self.valid = set(valid_tickers)
        self.db_url = DB_URL

    def save_post(self, post: Post) -> None:
        """Saves one post to the posts table of database.
        
        Args:
            post (Post): An instance of the Post dataclass.
        """
        conn = psycopg2.connect(self.db_url)
        cursor = conn.cursor()

        try:
            # Convert Unix timestamp to datetime (UTC)
            created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            # Convert author_created_utc to datetime if not None
            author_created_dt = None
            if post.author_created_utc is not None:
                author_created_dt = datetime.fromtimestamp(post.author_created_utc, tz=timezone.utc)
            cursor.execute("""
                INSERT INTO posts (post_id, subreddit, created_utc, text, type, origin_id, user_id, score, num_comments, author_created_utc, author_comment_karma, author_link_karma)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
                """, (post.id, post.subreddit, created_dt, post.text, post.type, post.origin_id, post.user_id, 
                      post.score, post.num_comments, author_created_dt, post.author_comment_karma, post.author_link_karma))
        
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving post {post.id}: {e}")
        finally:
            cursor.close()
            conn.close()

    def _batch_save_posts(self, posts_data: list[tuple]) -> None:
        """Batch saves multiple posts to the database in a single transaction.
        
        Args:
            posts_data: List of tuples (post_id, subreddit, created_utc, text, type, origin_id, user_id, score, num_comments, author_created_utc, author_comment_karma, author_link_karma)
        """
        if not posts_data:
            return

        conn = psycopg2.connect(self.db_url)
        cursor = conn.cursor()

        try:
            execute_batch(cursor, """
                INSERT INTO posts (post_id, subreddit, created_utc, text, type, origin_id, user_id, score, num_comments, author_created_utc, author_comment_karma, author_link_karma)
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
            conn.close()
    
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
            # Convert author_created_utc to datetime if not None
            author_created_dt = None
            if post.author_created_utc is not None:
                author_created_dt = datetime.fromtimestamp(post.author_created_utc, tz=timezone.utc)
            new_posts.append((post.id, post.subreddit, created_dt, post.text, post.type, post.origin_id, post.user_id,
                             post.score, post.num_comments, author_created_dt, post.author_comment_karma, post.author_link_karma))
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
        conn = psycopg2.connect(self.db_url)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT post_id FROM posts")
            existing_ids = {row[0] for row in cursor.fetchall()}
            return existing_ids
        finally:
            cursor.close()
            conn.close()