import sqlite3
from datetime import datetime
import sys
from pathlib import Path

# Add parent directory to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import MentionDataPoint

def insert_mention_counts(DB_PATH, mention_data_points: list[MentionDataPoint]):
    """Adds each MentionDataPoint to the database

    Args:
        DB_PATH (str): The database path
        mention_data_points (list[MentionDataPoint]): A list of MentionDataPoint objects to insert
    """
    if not mention_data_points:
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for data_point in mention_data_points:
        timestamp_str = data_point.timestamp.isoformat()
        cursor.execute("""
            INSERT OR IGNORE INTO mentions (ticker, subreddit, timestamp, mention_count)
            VALUES (?, ?, ?, ?);
        """, (data_point.ticker.upper(), data_point.subreddit, timestamp_str, data_point.mention_count))
    
    conn.commit()
    conn.close()

def fetch_ticker_mentions(DB_PATH, ticker: str, start_date: datetime, end_date: datetime) -> list[MentionDataPoint]:
    """Return a list of MentionDataPoint objects for a ticker between start_date and end_date.

        Args:
            ticker (str): Stock ticker symbol to search for.
            start_date (datetime): Start of the date range.
            end_date (datetime): End of the date range.

        Returns:
            list[MentionDataPoint]: A list of MentionDataPoint objects matching the criteria.
        """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
    SELECT ticker, subreddit, timestamp, mention_count FROM mentions
    WHERE ticker = ? 
    AND timestamp BETWEEN ? and ?
    ORDER BY timestamp
    """

    cursor.execute(query, (ticker.upper(), start_date.isoformat(), end_date.isoformat()))
    rows = cursor.fetchall()

    conn.close()

    # Convert database rows to MentionDataPoint objects
    mention_data_points = []
    for ticker_val, subreddit, timestamp_str, count in rows:
        # Parse ISO format timestamp string back to datetime
        timestamp = datetime.fromisoformat(timestamp_str)
        mention_data_points.append(
            MentionDataPoint(
                ticker=ticker_val,
                subreddit=subreddit,
                timestamp=timestamp,
                mention_count=int(count)
            )
        )
    
    return mention_data_points


    