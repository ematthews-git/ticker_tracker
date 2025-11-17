import re
import sqlite3
import psycopg2
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import config and models
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_URL
from models import Post, MentionDataPoint

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

    def save_post(self, post: Post):
        """Saves one post to the posts table of database.
        
        Args:
            post (Post): An instance of the Post dataclass.
        """
        conn = psycopg2.connect(self.db_url)
        cursor = conn.cursor()

        try:
            # Convert Unix timestamp to datetime
            created_dt = datetime.utcfromtimestamp(post.created_utc)
            cursor.execute("""
                INSERT INTO posts (post_id, subreddit, created_utc, text, type)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
                """, (post.id, post.subreddit, created_dt, post.text, post.type))
        
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error saving post {post.id}: {e}")
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
        timestamp = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

        #get existing posts to avoid double counting
        existing_ids = set()
        existing_ids = self._get_existing_posts_ids()
        print(f"Found {len(existing_ids)} existing posts in database")

        new_posts = 0

        for post in post_list:
            #skip if already processed
            if post.id in existing_ids:
                continue

            self.save_post(post)
            new_posts += 1

            #find ticker mentions
            tickers = re.findall(r'\b[A-Z]{2,5}\b', post.text) #captal letters + 2 to 5 characters
            for t in tickers:
                if t in self.valid:
                    key = (t.upper(), post.subreddit)
                    counts[key] = counts.get(key, 0) + 1 #existing val += 1
            
        print(f"{new_posts} New posts processed")
        
        # Convert counts dictionary to list of MentionDataPoint objects
        mention_data_points = [
            MentionDataPoint(
                ticker=ticker,
                subreddit=subreddit,
                timestamp=timestamp,
                mention_count=count
            )
            for (ticker, subreddit), count in counts.items()
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