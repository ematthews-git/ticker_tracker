import sqlite3
from datetime import datetime
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_batch

# Add parent directory to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import MentionDataPoint
import logging
logger = logging.getLogger(__name__)

def insert_mention_counts(db_url, mention_data_points: list[MentionDataPoint]) -> None:
    """Adds each MentionDataPoint to the database.

    Args:
        db_url (str): The PostgreSQL connection string.
        mention_data_points (list[MentionDataPoint]): A list of MentionDataPoint objects to insert.
    """
    if not mention_data_points:
        return

    #connect to db
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    try:
        #gets a list of every data point to be added, with variables prepared for SQL batch insert
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
        logger.error(f"Error inserting mention counts: {e}")
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

        #constructs the list of mentionDataPoints 
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
        logger.error(f"Error fetching data: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
    
def fetch_popular_tickers(db_url: str, start_date: datetime, end_date: datetime, amount: int=10) -> dict[str, list[MentionDataPoint]]:
    """Gets a list of the most popular tickers in a timeframe.

    Args:
        db_url (str): The connection URL to the database.
        start_date (datetime): The start of the date range to query.
        end_date (datetime): The end of the date range to query.
        amount (int, optional): The number of tickers to be returned. Defaults to 10.

    Returns:
        dict[str, list[MentionDataPoint]]: Maps a ticker to every point where it was mentioned for the given paramaters, 
                                            ordered where the first index is the most popular.
    """

    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    try: 
        #First gets the top tickers and their total mentions ordered by total mentions
        #Then using the top tickers to get each tickers mentionDataPoints to return
        cursor.execute("""
            WITH top_tickers AS (
                SELECT
                    ticker,
                    SUM(mention_count) AS total_mentions
                FROM mentions
                WHERE timestamp BETWEEN %s and %s
                GROUP by ticker
                ORDER by total_mentions DESC
                LIMIT %s
            )
            SELECT m.ticker, m.subreddit, m.timestamp, m.mention_count
            FROM mentions m
            JOIN top_tickers t ON m.ticker = t.ticker
            WHERE m.timestamp BETWEEN %s and %s
            ORDER BY t.total_mentions DESC, m.ticker, m.timestamp;
        """, (start_date, end_date, amount, start_date, end_date))

        rows = cursor.fetchall()
        logger.debug(f"[DEBUG] Final query returned {len(rows)} rows")
        result = dict()

        #construct return object
        for ticker, subreddit, timestamp, count in rows:
            dp = MentionDataPoint(
                ticker=ticker,
                subreddit=subreddit,
                timestamp=timestamp,
                mention_count=count
            )
            if ticker not in result:
                result[ticker] = []
            result[ticker].append(dp)
        
        return result
    except Exception as e:
        logger.error(f"Error fetching popular tickers: {e}")
        raise
    finally:
        cursor.close()
        conn.close()