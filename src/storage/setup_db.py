import sqlite3
import os
import sys
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH

print(DB_PATH)

def create_database():
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
                   PRIMARY KEY (ticker, subreddit, timestamp)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
                   post_id TEXT PRIMARY KEY,
                   subreddit TEXT NOT NULL,
                   created_utc DATETIME NOT NULL,
                   text TEXT NOT NULL,
                   type TEXT NOT NULL
        );
    """)

    conn.commit()
    conn.close()
    print("Database and tables created successfully.")

if __name__ == "__main__":
    create_database()