from datetime import datetime, timedelta, timezone
from psycopg2.extras import execute_batch

from models import MentionDataPoint
import logging

logger = logging.getLogger(__name__)


def insert_mention_counts(
    connection_pool, mention_data_points: list[MentionDataPoint]
) -> None:
    """Adds each MentionDataPoint to the database.

    Two-step write: dedupe users via mention_users (PK rejects duplicates across
    upserts), then upsert the mentions rollup. mention_count / sentiment_sum /
    post_count / total_score / total_comments are additive — safe because the
    scanner only emits MDPs for posts that weren't seen before. unique_users is
    recomputed from mention_users so the same user across :00 and :30 runs in
    one hour bucket counts once. avg_sentiment is a generated column.

    Args:
        connection_pool: The PostgreSQL connection pool.
        mention_data_points (list[MentionDataPoint]): A list of MentionDataPoint objects to insert.
    """
    if not mention_data_points:
        return

    conn = connection_pool.getconn()
    cursor = conn.cursor()

    try:
        user_rows = [
            (mdp.ticker.upper(), mdp.subreddit, mdp.timestamp, uid)
            for mdp in mention_data_points
            for uid in mdp.user_ids
        ]
        if user_rows:
            execute_batch(
                cursor,
                """
                INSERT INTO mention_users (ticker, subreddit, timestamp, user_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                user_rows,
            )

        mention_rows = [
            (
                mdp.ticker.upper(),
                mdp.subreddit,
                mdp.timestamp,
                mdp.mention_count,
                mdp.total_score,
                mdp.total_comments,
                mdp.sentiment_sum,
                mdp.post_count,
                len(mdp.user_ids),
                # avg_sentiment for new-row insert; on conflict the column is
                # recomputed from the merged sums so this only matters first time.
                (mdp.sentiment_sum / mdp.post_count) if mdp.post_count else 0.0,
            )
            for mdp in mention_data_points
        ]

        execute_batch(
            cursor,
            """
            INSERT INTO mentions (
                ticker, subreddit, timestamp,
                mention_count, total_score, total_comments,
                sentiment_sum, post_count, unique_users, avg_sentiment
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, subreddit, timestamp) DO UPDATE SET
                mention_count  = mentions.mention_count  + EXCLUDED.mention_count,
                total_score    = mentions.total_score    + EXCLUDED.total_score,
                total_comments = mentions.total_comments + EXCLUDED.total_comments,
                sentiment_sum  = mentions.sentiment_sum  + EXCLUDED.sentiment_sum,
                post_count     = mentions.post_count     + EXCLUDED.post_count,
                avg_sentiment  = CASE
                    WHEN (mentions.post_count + EXCLUDED.post_count) = 0 THEN 0
                    ELSE (mentions.sentiment_sum + EXCLUDED.sentiment_sum)
                         / (mentions.post_count + EXCLUDED.post_count)
                END,
                unique_users   = (
                    SELECT COUNT(*) FROM mention_users
                    WHERE ticker = EXCLUDED.ticker
                      AND subreddit = EXCLUDED.subreddit
                      AND timestamp = EXCLUDED.timestamp
                )
            """,
            mention_rows,
        )

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error inserting mention counts: {e}")
        raise
    finally:
        cursor.close()
        connection_pool.putconn(conn)


def fetch_ticker_mentions(
    connection_pool, ticker: str, start_date: datetime, end_date: datetime
) -> list[MentionDataPoint]:
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

        # constructs the list of mentionDataPoints
        mention_data_points = []
        for (
            ticker_val,
            subreddit,
            timestamp,
            count,
            unique_users,
            total_score,
            total_comments,
            avg_sentiment,
        ) in rows:
            mention_data_points.append(
                MentionDataPoint(
                    ticker=ticker_val,
                    subreddit=subreddit,
                    timestamp=timestamp,
                    mention_count=int(count),
                    unique_users=int(unique_users),
                    total_score=int(total_score),
                    total_comments=int(total_comments),
                    avg_sentiment=float(avg_sentiment),
                )
            )

        return mention_data_points
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        raise
    finally:
        cursor.close()
        connection_pool.putconn(conn)


def fetch_popular_tickers(
    connection_pool, start_date: datetime, end_date: datetime, amount: int = 10
) -> dict[str, list[MentionDataPoint]]:
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
        # First gets the top tickers and their total mentions ordered by total mentions
        # Then using the top tickers to get each tickers mentionDataPoints to return
        cursor.execute(
            """
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
        """,
            (start_date, end_date, amount, start_date, end_date),
        )

        rows = cursor.fetchall()
        logger.debug(f"[DEBUG] Final query returned {len(rows)} rows")
        result = dict()

        # construct return object
        for (
            ticker,
            subreddit,
            timestamp,
            count,
            unique_users,
            total_score,
            total_comments,
            avg_sentiment,
        ) in rows:
            dp = MentionDataPoint(
                ticker=ticker,
                subreddit=subreddit,
                timestamp=timestamp,
                mention_count=int(count),
                unique_users=int(unique_users),
                total_score=int(total_score),
                total_comments=int(total_comments),
                avg_sentiment=float(avg_sentiment),
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


def fetch_growth_tickers(
    connection_pool, start_date: datetime, end_date: datetime, amount: int = 10
) -> dict[str, tuple[float, list[MentionDataPoint]]]:
    """Gets tickers with the highest growth in mentions between two time periods.

    Compares the first half of the date range to the second half to calculate growth.
    Growth is calculated as: (recent_mentions - older_mentions) / older_mentions * 100

    Args:
        connection_pool: The PostgreSQL connection pool.
        start_date (datetime): The start of the date range to query.
        end_date (datetime): The end of the date range to query.
        amount (int, optional): The number of tickers to be returned. Defaults to 10.

    Returns:
        dict[str, tuple[float, list[MentionDataPoint]]]: Maps a ticker to a tuple of (growth_rate, mention_points),
                                                          ordered where the first index has the highest growth.
    """
    conn = connection_pool.getconn()
    cursor = conn.cursor()

    try:
        # Calculate midpoint to split the date range in half
        time_diff = end_date - start_date
        midpoint = start_date + (time_diff / 2)

        # Query to calculate growth for each ticker
        cursor.execute(
            """
            WITH period_mentions AS (
                SELECT
                    ticker,
                    CASE
                        WHEN timestamp < %s THEN 'older'
                        ELSE 'recent'
                    END AS period,
                    SUM(mention_count) AS total_mentions
                FROM mentions
                WHERE timestamp BETWEEN %s AND %s
                GROUP BY ticker, period
            ),
            growth_calc AS (
                SELECT
                    ticker,
                    MAX(CASE WHEN period = 'older' THEN total_mentions ELSE 0 END) AS older_mentions,
                    MAX(CASE WHEN period = 'recent' THEN total_mentions ELSE 0 END) AS recent_mentions
                FROM period_mentions
                GROUP BY ticker
            ),
            ticker_growth AS (
                SELECT
                    ticker,
                    older_mentions,
                    recent_mentions,
                    CASE
                        WHEN older_mentions = 0 AND recent_mentions > 0 THEN 999999
                        WHEN older_mentions = 0 THEN 0
                        ELSE ((recent_mentions - older_mentions)::FLOAT / older_mentions * 100)
                    END AS growth_rate
                FROM growth_calc
                WHERE recent_mentions > 0  -- Only include tickers with recent activity
                ORDER BY growth_rate DESC
                LIMIT %s
            )
            SELECT m.ticker, m.subreddit, m.timestamp, m.mention_count, m.unique_users,
                   m.total_score, m.total_comments, m.avg_sentiment, tg.growth_rate
            FROM mentions m
            JOIN ticker_growth tg ON m.ticker = tg.ticker
            WHERE m.timestamp BETWEEN %s AND %s
            ORDER BY tg.growth_rate DESC, m.ticker, m.timestamp;
        """,
            (midpoint, start_date, end_date, amount, start_date, end_date),
        )

        rows = cursor.fetchall()
        logger.debug(f"Growth query returned {len(rows)} rows")
        result = dict()
        ticker_growth_rates = {}  # Store growth rate for each ticker

        # Construct return object
        for (
            ticker,
            subreddit,
            timestamp,
            count,
            unique_users,
            total_score,
            total_comments,
            avg_sentiment,
            growth_rate,
        ) in rows:
            dp = MentionDataPoint(
                ticker=ticker,
                subreddit=subreddit,
                timestamp=timestamp,
                mention_count=int(count),
                unique_users=int(unique_users),
                total_score=int(total_score),
                total_comments=int(total_comments),
                avg_sentiment=float(avg_sentiment),
            )
            if ticker not in result:
                result[ticker] = []
                ticker_growth_rates[ticker] = float(growth_rate)
            result[ticker].append(dp)

        # Convert result to include growth rates
        final_result = {
            ticker: (ticker_growth_rates[ticker], mention_points)
            for ticker, mention_points in result.items()
        }

        return final_result
    except Exception as e:
        logger.error(f"Error fetching growth tickers: {e}")
        raise
    finally:
        cursor.close()
        connection_pool.putconn(conn)


def fetch_recent_post_ids(
    connection_pool, lookback_hours: int, limit: int
) -> list[tuple[str, str]]:
    """Returns (post_id, subreddit) for the most-discussed posts from the last N hours.

    Used by collect_older_comments() to identify posts worth re-checking for new comments.

    Args:
        connection_pool: The PostgreSQL connection pool.
        lookback_hours (int): How many hours back to search.
        limit (int): Maximum number of posts to return.

    Returns:
        list[tuple[str, str]]: List of (post_id, subreddit) ordered by num_comments desc.
    """

    conn = connection_pool.getconn()
    cursor = conn.cursor()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        cursor.execute(
            """
            SELECT post_id, subreddit FROM posts
            WHERE type = 'post'
              AND created_utc >= %s
            ORDER BY num_comments DESC
            LIMIT %s
            """,
            (cutoff, limit),
        )
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error fetching recent post IDs: {e}")
        return []
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
        cursor.execute(
            """
            SELECT post_id FROM posts
            WHERE post_id = ANY(SELECT unnest(%s::text[]))
            """,
            (post_ids,),
        )
        return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"Error checking existing posts batch: {e}")
        return set()
    finally:
        cursor.close()
        connection_pool.putconn(conn)
