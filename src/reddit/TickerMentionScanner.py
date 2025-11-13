import re
import sqlite3
from config import DB_PATH
from models import Post

class TickerMentionScanner:
    """Scans for Ticker Mentions and saves posts to database
    """
    def __init__(self, invalid_tickers):
        
        self.invalid = set(invalid_tickers)

    def save_post(self, post: Post):
        """Saves one post to the posts table of database
        
        Args:
            post (Post): An instance of the Post dataclass
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO posts (post_id, type, text, created_utc)
            VALUES (?, ?, ?, ?)
            """, (post.id, post.type, post.text, post.created_utc))
        
        conn.commit()
        conn.close()
    
    #Counts mentions of valid tickers into dictionary from a list of text
    def process_mentions(self, post_list: list[Post]) -> dict[str, int]:
        """finds the mention of any valid ticker in the list of text parsed and saves each post to db.

        Args:
            post_list (Iterable[Post]): The list of post items to search.

        Returns:
            dict[str, int]: A dictionary mapping each ticker symbol to the number of times it was mentioned.
        """
        counts = {}

        for post in post_list:
            self.save_post(post)
            #find ticker mentions
            tickers = re.findall(r'\b[A-Z]{2, 5}\b', post.text) #captal letters + 2 to 5 characters
            for t in tickers:
                if t not in self.invalid:
                    counts[t] = counts.get(t, 0) + 1 #existing val += 1
            return counts