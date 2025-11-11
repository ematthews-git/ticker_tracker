import re
import sqlite3
from config import DB_PATH

class TickerMentionScanner:
    """Scans for Ticker Mentions and saves posts to database
    """
    def __init__(self, invalid_tickers):
        
        self.invalid = set(invalid_tickers)

    def save_post(self, post):
        """Saves one post to the posts table of database
        
        Args:
            post (dict): defined by:
                - {"id"(str), "type"(str), "text"(str), "created"(float)}
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO posts (id, type, text, created_utc)
            VALUES (?, ?, ?)
            """, (post["id"], post["type"], post["text"], post["created"]))
        
        conn.commit()
        conn.close()
    
    #Counts mentions of valid tickers into dictionary from a list of text
    def count_mentions(self, post_list) -> dict:
        """finds the mention of any valid ticker in the list of text parsed

        Post is a dict object defined by the folliwing:
            - {"id"(str), "type"(str), "text"(str), "created"(float)}

        Args:
            post_list (Iterable[post]): The list of text items to search

        Returns:
            dict[str, int]: A dictionary mapping each ticker symbol to the number of times it was mentioned
        """
        counts = {}

        for post in post_list:
            print("67")

        # for text in text_list:
        #     words = re.findall(r'\b[A-Z]{2,5}\b', text) #capital letters + 2 to 5 characters
        #     for w in words:
        #         if w not in self.invalid:
        #             counts[w] = counts.get(w, 0) + 1 #existing val += 1
        # return counts