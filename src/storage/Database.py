from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_batch
from typing import Optional, Tuple

# Add parent directory to path to import models
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import MentionDataPoint, Author
import logging
logger = logging.getLogger(__name__)

def insert_mention_counts(connection_pool, mention_data_points: list[MentionDataPoint]) -> None:
    """Adds each MentionDataPoint to the database.

    Args:
        connection_pool: The PostgreSQL connection pool.
        mention_data_points (list[MentionDataPoint]): A list of MentionDataPoint objects to insert.
    """
    if not mention_data_points:
        return

    #get connection from pool
    conn = connection_pool.getconn()
    cursor = conn.cursor()

    try:
        #gets a list of every data point to be added, with variables prepared for SQL batch insert
        data = [
            (data_point.ticker.upper(),
             data_point.subreddit,
             data_point.timestamp,
             data_point.mention_count,
             data_point.unique_users,
             data_point.total_score,
             data_point.total_comments,
             data_point.avg_sentiment)
             for data_point in mention_data_points
        ]

        execute_batch(cursor, """
            INSERT INTO mentions (ticker, subreddit, timestamp, mention_count, unique_users, total_score, total_comments, avg_sentiment)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, subreddit, timestamp) DO NOTHING
            """, data)
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error inserting mention counts: {e}")
        raise
    finally:
        cursor.close()
        connection_pool.putconn(conn)
    

def fetch_ticker_mentions(connection_pool, ticker: str, start_date: datetime, end_date: datetime) -> list[MentionDataPoint]:
    """Return a list of MentionDataPoint objects for a ticker between start_date and end_date.

        Args:
            connection_pool: The PostgreSQL connection pool.
            ticker (str): Stock ticker symbol to search for.
            start_date (datetime): Start of the date range.
            end_date (datetime): End of the date range.

        Returns:
            list[MentionDataPoint]: A list of MentionDataPoint objects matching the criteria.
        """
    
    conn = connection_pool.getconn()
    cursor = conn.cursor()

    try:
        query = """
        SELECT ticker, subreddit, timestamp, mention_count, unique_users, total_score, total_comments, avg_sentiment FROM mentions
        WHERE ticker = %s
        AND timestamp BETWEEN %s and %s
        ORDER BY timestamp
        """

        cursor.execute(query, (ticker.upper(), start_date, end_date))
        rows = cursor.fetchall()
        
        #constructs the list of mentionDataPoints 
        mention_data_points = []
        for ticker_val, subreddit, timestamp, count, unique_users, total_score, total_comments, avg_sentiment in rows:
            mention_data_points.append(
                MentionDataPoint(
                    ticker=ticker_val,
                    subreddit=subreddit,
                    timestamp=timestamp,
                    mention_count=int(count),
                    unique_users=int(unique_users),
                    total_score=int(total_score),
                    total_comments=int(total_comments),
                    avg_sentiment=float(avg_sentiment)
                )
            )
    
        return mention_data_points
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        raise
    finally:
        cursor.close()
        connection_pool.putconn(conn)
    
def fetch_popular_tickers(connection_pool, start_date: datetime, end_date: datetime, amount: int=10) -> dict[str, list[MentionDataPoint]]:
    """Gets a list of the most popular tickers in a timeframe.

    Args:
        connection_pool: The PostgreSQL connection pool.
        start_date (datetime): The start of the date range to query.
        end_date (datetime): The end of the date range to query.
        amount (int, optional): The number of tickers to be returned. Defaults to 10.

    Returns:
        dict[str, list[MentionDataPoint]]: Maps a ticker to every point where it was mentioned for the given paramaters, 
                                            ordered where the first index is the most popular.
    """

    conn = connection_pool.getconn()
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
            SELECT m.ticker, m.subreddit, m.timestamp, m.mention_count, m.unique_users, m.total_score, m.total_comments, m.avg_sentiment
            FROM mentions m
            JOIN top_tickers t ON m.ticker = t.ticker
            WHERE m.timestamp BETWEEN %s and %s
            ORDER BY t.total_mentions DESC, m.ticker, m.timestamp;
        """, (start_date, end_date, amount, start_date, end_date))

        rows = cursor.fetchall()
        logger.debug(f"[DEBUG] Final query returned {len(rows)} rows")
        result = dict()

        #construct return object
        for ticker, subreddit, timestamp, count, unique_users, total_score, total_comments, avg_sentiment in rows:
            dp = MentionDataPoint(
                ticker=ticker,
                subreddit=subreddit,
                timestamp=timestamp,
                mention_count=int(count),
                unique_users=int(unique_users),
                total_score=int(total_score),
                total_comments=int(total_comments),
                avg_sentiment=float(avg_sentiment)
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
        connection_pool.putconn(conn)

def get_author_data(connection_pool, username: str) -> Optional[Author]:
    """Get cached author data from database if it exists and is fresh (< 7 days old).
    
    Args:
        connection_pool: The PostgreSQL connection pool.
        username (str): The Reddit username to look up.
        
    Returns:
        Optional[Author]: Author object if cache hit and fresh, None if cache miss or stale.
    """
    conn = connection_pool.getconn()
    cursor = conn.cursor()
    
    try:
        # Check if author exists and cache is less than 7 days old
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        cursor.execute("""
            SELECT username, created_utc, comment_karma, link_karma, last_updated
            FROM authors
            WHERE username = %s AND last_updated >= %s
        """, (username, seven_days_ago))
        
        row = cursor.fetchone()
        if row:
            username_val, created_utc_dt, comment_karma, link_karma, last_updated = row
            # Handle None values - use defaults if missing
            created_utc = created_utc_dt if created_utc_dt is not None else datetime.fromtimestamp(0, tz=timezone.utc)
            comment_karma_val = comment_karma if comment_karma is not None else 0
            link_karma_val = link_karma if link_karma is not None else 0
            last_updated_val = last_updated if last_updated is not None else datetime.now(timezone.utc)
            
            return Author(
                username=username_val,
                created_utc=created_utc,
                comment_karma=comment_karma_val,
                link_karma=link_karma_val,
                last_updated=last_updated_val
            )
        return None
    except Exception as e:
        logger.error(f"Error getting author data for {username}: {e}")
        return None
    finally:
        cursor.close()
        connection_pool.putconn(conn)


def upsert_author_data(connection_pool, author: Author) -> None:
    """Insert or update author data in the cache.
    
    Args:
        connection_pool: The PostgreSQL connection pool.
        author (Author): Author object to insert or update.
    """
    conn = connection_pool.getconn()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO authors (username, created_utc, comment_karma, link_karma, last_updated)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (username) 
            DO UPDATE SET 
                created_utc = EXCLUDED.created_utc,
                comment_karma = EXCLUDED.comment_karma,
                link_karma = EXCLUDED.link_karma,
                last_updated = NOW()
        """, (author.username, author.created_utc, author.comment_karma, author.link_karma))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error upserting author data for {author.username}: {e}")
        raise
    finally:
        cursor.close()
        connection_pool.putconn(conn)


def fetch_growth_tickers(connection_pool) -> dict[str, list[MentionDataPoint]]:

    conn = connection_pool.getconn()
    cursor = conn.cursor()

    try:
        # Get tickers with positive growth in mentions
        # This is a placeholder for more complex logic
        cursor.execute("""
            SELECT ticker, SUM(mention_count) as total_mentions
            FROM mentions
            GROUP BY ticker
            ORDER BY total_mentions DESC
            LIMIT 5
        """)
        
        # For now just return empty dict as this seems to be a work in progress
        return {}
    except Exception as e:
        logger.error(f"Error fetching growth tickers: {e}")
        return {}
    finally:
        cursor.close()
        connection_pool.putconn(conn)

def get_authors_batch(connection_pool, usernames: list[str]) -> dict[str, Author]:
    """Get cached author data for a list of usernames.
    
    Args:
        connection_pool: The PostgreSQL connection pool.
        usernames (list[str]): List of usernames to look up.
        
    Returns:
        dict[str, Author]: Dictionary mapping username to Author object for found authors.
    """
    if not usernames:
        return {}
        
    conn = connection_pool.getconn()
    cursor = conn.cursor()
    
    try:
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        # Use ANY for batch selection
        cursor.execute("""
            SELECT username, created_utc, comment_karma, link_karma, last_updated
            FROM authors
            WHERE username = ANY(%s) AND last_updated >= %s
        """, (usernames, seven_days_ago))
        
        results = {}
        for row in cursor.fetchall():
            username_val, created_utc_dt, comment_karma, link_karma, last_updated = row
            
            # Handle None values
            created_utc = created_utc_dt if created_utc_dt is not None else datetime.fromtimestamp(0, tz=timezone.utc)
            comment_karma_val = comment_karma if comment_karma is not None else 0
            link_karma_val = link_karma if link_karma is not None else 0
            last_updated_val = last_updated if last_updated is not None else datetime.now(timezone.utc)
            
            results[username_val] = Author(
                username=username_val,
                created_utc=created_utc,
                comment_karma=comment_karma_val,
                link_karma=link_karma_val,
                last_updated=last_updated_val
            )
            
        return results
    except Exception as e:
        logger.error(f"Error getting batch author data: {e}")
        return {}
    finally:
        cursor.close()
        connection_pool.putconn(conn)

def get_existing_post_ids_batch(connection_pool, post_ids: list[str]) -> set[str]:
    """Check which post IDs from the list already exist in the database.
    
    Args:
        connection_pool: The PostgreSQL connection pool.
        post_ids (list[str]): List of post IDs to check.
        
    Returns:
        set[str]: Set of post IDs that already exist.
    """
    if not post_ids:
        return set()
        
    conn = connection_pool.getconn()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT post_id FROM posts WHERE post_id = ANY(%s)
        """, (post_ids,))
        
        return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"Error checking existing posts batch: {e}")
        return set()
    finally:
        cursor.close()
        connection_pool.putconn(conn)