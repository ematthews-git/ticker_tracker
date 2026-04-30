import psycopg2

from config import DB_URL


def create_database_postgres(db_url):

    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    # mentions rollup. sentiment_sum / post_count are the raw inputs that let
    # the upsert recompute a correctly-weighted avg_sentiment on conflict.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mentions (
                   ticker TEXT NOT NULL,
                   subreddit TEXT NOT NULL,
                   timestamp TIMESTAMPTZ NOT NULL,
                   mention_count INTEGER NOT NULL,
                   total_score INTEGER NOT NULL,
                   total_comments INTEGER NOT NULL,
                   sentiment_sum REAL NOT NULL DEFAULT 0,
                   post_count INTEGER NOT NULL DEFAULT 0,
                   unique_users INTEGER NOT NULL DEFAULT 0,
                   avg_sentiment REAL NOT NULL DEFAULT 0,
                   PRIMARY KEY (ticker, subreddit, timestamp)
        );
        """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_ticker_timestamp
        ON mentions(ticker, timestamp DESC);
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_subreddit_timestamp
        ON mentions(subreddit, timestamp DESC);
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_timestamp
        ON mentions(timestamp DESC);
    """)

    # mention_users: PK dedupes a user across upserts within a bucket so
    # unique_users in the rollup can be recomputed correctly on conflict.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mention_users (
                   ticker TEXT NOT NULL,
                   subreddit TEXT NOT NULL,
                   timestamp TIMESTAMPTZ NOT NULL,
                   user_id TEXT NOT NULL,
                   PRIMARY KEY (ticker, subreddit, timestamp, user_id)
        );
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mention_users_bucket
        ON mention_users(ticker, subreddit, timestamp);
    """)

    # post_mentions: per-post -> ticker map. Lets the rollup be re-derived
    # from the posts table if regex or valid_tickers ever changes.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_mentions (
                   post_id TEXT NOT NULL,
                   ticker TEXT NOT NULL,
                   PRIMARY KEY (post_id, ticker)
        );
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_post_mentions_ticker
        ON post_mentions(ticker);
    """)

    # posts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
                   post_id TEXT PRIMARY KEY,
                   subreddit TEXT NOT NULL,
                   created_utc TIMESTAMPTZ NOT NULL,
                   text TEXT NOT NULL,
                   link_flair_text TEXT,
                   type TEXT NOT NULL,
                   origin_id TEXT,
                   user_id TEXT NOT NULL,
                   score INTEGER NOT NULL,
                   upvote_ratio REAL,
                   num_comments INTEGER NOT NULL,
                   author_quality REAL
        );
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_posts_subreddit
        ON posts(subreddit);
    """)

    # stock_prices table for storing hourly OHLCV data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_prices (
                   ticker TEXT NOT NULL,
                   timestamp TIMESTAMPTZ NOT NULL,
                   open REAL NOT NULL,
                   high REAL NOT NULL,
                   low REAL NOT NULL,
                   close REAL NOT NULL,
                   volume BIGINT NOT NULL,
                   PRIMARY KEY (ticker, timestamp)
        );
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_prices_ticker_timestamp
        ON stock_prices(ticker, timestamp DESC);
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_prices_timestamp
        ON stock_prices(timestamp DESC);
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("database created")


if __name__ == "__main__":
    # create_database_sqlite()
    create_database_postgres(DB_URL)
