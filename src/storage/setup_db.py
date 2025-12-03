import sqlite3
import os
import psycopg2

from config import DB_PATH, DB_URL

print(DB_URL)

def create_database_postgres(db_url):

    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    #create mentions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mentions (
                   ticker TEXT NOT NULL,
                   subreddit TEXT NOT NULL,
                   timestamp TIMESTAMPTZ NOT NULL,
                   mention_count INTEGER NOT NULL,
                   unique_users INTEGER NOT NULL,
                   total_score INTEGER NOT NULL,
                   total_comments INTEGER NOT NULL,
                   avg_sentiment REAL NOT NULL,
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
    
    # For Discord bot: composite index for specific ticker+subreddit queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mentions_ticker_subreddit_timestamp 
        ON mentions(ticker, subreddit, timestamp DESC);
    """)

    #posts
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

    #authors table for caching Reddit author data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS authors (
                   username TEXT PRIMARY KEY,
                   created_utc TIMESTAMPTZ,
                   comment_karma INTEGER,
                   link_karma INTEGER,
                   last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_authors_last_updated 
        ON authors(last_updated DESC);
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("database created")

def create_database_sqlite():
    """Creates database with:
    mentions table and posts table
    """
    #TODO: check path is valid

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mentions (
                   ticker TEXT NOT NULL,
                   subreddit TEXT NOT NULL,
                   timestamp DATETIME NOT NULL,
                   mention_count INTEGER NOT NULL,
                   unique_users INTEGER NOT NULL,
                   total_score INTEGER NOT NULL,
                   total_comments INTEGER NOT NULL,
                   avg_sentiment REAL NOT NULL,
                   PRIMARY KEY (ticker, subreddit, timestamp)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
                   post_id TEXT PRIMARY KEY,
                   subreddit TEXT NOT NULL,
                   created_utc DATETIME NOT NULL,
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

    #authors table for caching Reddit author data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS authors (
                   username TEXT PRIMARY KEY,
                   created_utc DATETIME,
                   comment_karma INTEGER,
                   link_karma INTEGER,
                   last_updated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_authors_last_updated 
        ON authors(last_updated DESC);
    """)

    conn.commit()
    conn.close()
    print("Database and tables created successfully.")

if __name__ == "__main__":
    #create_database_sqlite()
    create_database_postgres(DB_URL)