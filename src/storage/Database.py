import sqlite3
from datetime import datetime

def insert_mention_counts(DB_PATH, counts):
    """Adds each ticker in counts to the database with a timestamp

    Args:
        DB_PATH (str): The database path
        counts (dict[tuple[str, str], int]): A dictionary mapping (ticker, subreddit) tuples to mention counts
    """

    now = datetime.utcnow()
    timestamp = now.replace(minute=0, second=0, microsecond=0).isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for (ticker, subreddit), count in counts.items():
        cursor.execute("""
            INSERT OR IGNORE INTO mentions (ticker, subreddit, timestamp, mention_count)
            VALUES (?, ?, ?, ?);
        """, (ticker.upper(), subreddit, timestamp, count))
    
    conn.commit()
    conn.close()

def fetch_ticker_mentions(DB_PATH, ticker: str, start_date: datetime, end_date: datetime) -> set[tuple[str, str, int]]:
    """Return a set of all mention IDs for a ticker between start_date and end_date.

        Args:
            ticker (str): Stock ticker symbol to search for.
            start_date (datetime): Start of the date range.
            end_date (datetime): End of the date range.

        Returns:
            Set[str, str, int]: (timestamp, subreddit, count)
        """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
    SELECT timestamp, subreddit, mention_count FROM mentions
    WHERE ticker = ? 
    AND timestamp BETWEEN ? and ?
    """

    cursor.execute(query, (ticker.upper(), start_date.isoformat(), end_date.isoformat()))
    rows = cursor.fetchall()

    conn.close()

    return {(ts, sub, int(count)) for ts, sub, count in rows}


    