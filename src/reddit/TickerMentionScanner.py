import re
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path to import config and models
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH
from models import Post

class TickerMentionScanner:
    """Scans for Ticker Mentions and saves posts to database.
    """
    def __init__(self, invalid_tickers):
        
        self.invalid = set(invalid_tickers)

    def save_post(self, post: Post):
        """Saves one post to the posts table of database.
        
        Args:
            post (Post): An instance of the Post dataclass.
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO posts (post_id, subreddit, type, text, created_utc)
            VALUES (?, ?, ?, ?, ?)
            """, (post.id, post.subreddit, post.type, post.text, post.created_utc))
        
        conn.commit()
        conn.close()
    
    #Counts mentions of valid tickers into dictionary from a list of text
    def process_mentions(self, post_list: list[Post]) -> dict[tuple[str, str], int]:
        """finds the mention of any valid ticker in the list of text parsed and saves each post to db.

        Args:
            post_list (Iterable[Post]): The list of post items to search.

        Returns:
            dict[tuple[str, str], int]: A dictionary mapping (ticker, subreddit) tuples to mention counts.
        """
        counts = {}

        for post in post_list:
            self.save_post(post)
            #find ticker mentions
            tickers = re.findall(r'\b[A-Z]{2,5}\b', post.text) #captal letters + 2 to 5 characters
            for t in tickers:
                if t not in self.invalid:
                    key = (t, post.subreddit)
                    counts[key] = counts.get(key, 0) + 1 #existing val += 1

        return counts