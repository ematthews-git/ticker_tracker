import sqlite3
from datetime import datetime

def insert_mention_counts(DB_PATH, counts):
    """Adds each ticker in counts to the database with a timestamp

    Args:
        DB_PATH (str): The database path
        counts (dict[str, int]): A dictionary holding a ticker and count value pair
    """
    timestamp = datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for ticker, count in counts:
        cursor.execute("""
            INSERT OR IGNORE INTO mentions (ticker, timestamp, mention_count)
            VALUES (?, ?, ?);
        """, (ticker.upper(), timestamp, count))
    
    conn.commit()
    conn.close()
