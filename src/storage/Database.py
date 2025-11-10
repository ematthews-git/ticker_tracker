import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_path="data.db"):
        self.connection = sqlite3.connect(db_path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS mentions (ticker TEXT, timestamp TEXT, mentions INTEGER)")
    
    def InsertMentionCounts(self, counts):
        timestamp = datetime.utcnow().isoformat()
        for ticker, value in counts.items():
            self.connection.execute(
                "INSERT INTO mentions values (?,?,?)", 
                (ticker, timestamp, value)
            )
        self.connection.commit()