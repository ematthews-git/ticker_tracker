import sqlite3
from datetime import datetime

def insert_mention_counts(DB_PATH, counts):
    """Adds each ticker in counts to the database with a timestamp

    Args:
        DB_PATH (str): The database path
        counts (dict[tuple[str, str], int]): A dictionary mapping (ticker, subreddit) tuples to mention counts
    """
    timestamp = datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for (ticker, subreddit), count in counts.items():
        cursor.execute("""
            INSERT OR IGNORE INTO mentions (ticker, subreddit, timestamp, mention_count)
            VALUES (?, ?, ?, ?);
        """, (ticker.upper(), subreddit, timestamp, count))
    
    conn.commit()
    conn.close()
