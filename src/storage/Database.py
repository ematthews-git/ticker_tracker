import sqlite3
from datetime import datetime

class Database:
    """The database holding each ticker, count value pair

    SQLite database which holds entries per timestamp. 
    EX: "TSLA", "2025-11-11 12:00:00", "300"
        "TSLA", "2025-11-11 13:00:00", "200"
    """
    def __init__(self, db_path="data.db"):
        self.connection = sqlite3.connect(db_path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS mentions (ticker TEXT, timestamp TEXT, mentions INTEGER)")
    
    def insert_mention_counts(self, counts):
        """Adds each ticker in counts to the database with a timestamp

        Args:
            counts (dict[str, int]): A dictionary holding a ticker and count value pair
        """
        timestamp = datetime.utcnow().isoformat()
        for ticker, value in counts.items():
            self.connection.execute(
                "INSERT INTO mentions values (?,?,?)", 
                (ticker, timestamp, value)
            )
        self.connection.commit()