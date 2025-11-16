import sqlite3
from datetime import datetime
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_batch

# Add parent directory to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import MentionDataPoint

def insert_mention_counts(db_url, mention_data_points: list[MentionDataPoint]):
    """Adds each MentionDataPoint to the database.

    Args:
        db_url (str): The PostgreSQL connection string.
        mention_data_points (list[MentionDataPoint]): A list of MentionDataPoint objects to insert.
    """
    if not mention_data_points:
        return

    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    try:
        data = [
            (data_point.ticker.upper(),
             data_point.subreddit,
             data_point.timestamp,
             data_point.mention_count)
             for data_point in mention_data_points
        ]

        execute_batch(cursor, """
            INSERT INTO mentions (ticker, subreddit, timestamp, mention_count)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (ticker, subreddit, timestamp) DO NOTHING
            """, data)
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error inserting mention counts: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
    

def fetch_ticker_mentions(db_url, ticker: str, start_date: datetime, end_date: datetime) -> list[MentionDataPoint]:
    """Return a list of MentionDataPoint objects for a ticker between start_date and end_date.

        Args:
            db_url (str): The PostgreSQL connection string.
            ticker (str): Stock ticker symbol to search for.
            start_date (datetime): Start of the date range.
            end_date (datetime): End of the date range.

        Returns:
            list[MentionDataPoint]: A list of MentionDataPoint objects matching the criteria.
        """
    
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    try:
        query = """
        SELECT ticker, subreddit, timestamp, mention_count FROM mentions
        WHERE ticker = %s
        AND timestamp BETWEEN %s and %s
        ORDER BY timestamp
        """

        cursor.execute(query, (ticker.upper(), start_date, end_date))
        rows = cursor.fetchall()

        mention_data_points = []
        for ticker_val, subreddit, timestamp, count in rows:
            mention_data_points.append(
                MentionDataPoint(
                    ticker=ticker_val,
                    subreddit=subreddit,
                    timestamp=timestamp,
                    mention_count=int(count)
                )
            )
    
        return mention_data_points
    except Exception as e:
        print(f"Error fetching data: {e}")
    finally:
        cursor.close()
        conn.close()
    


    