import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH")
print(DB_PATH)

def create_database():
    """Creates a database and table for mentions
    """
    #TODO: check path is valid

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mentions (
                   ticker TEXT NOT NULL,
                   timestamp DATETIME NOT NULL,
                   mention_count INTEGER NOT NULL,
                   PRIMARY KEY (ticker, timestamp)
        );
    """)

    conn.commit()
    conn.close()
    print("Database and tables created successfully.")

if __name__ == "__main__":
    create_database()