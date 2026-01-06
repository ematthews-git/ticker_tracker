from datetime import datetime, timedelta, timezone
from typing import Optional


def parse_time_input(timeframe: str) -> timedelta:
    """Converts a string into a representative timedelta

    Args:
        timeframe (str): Examples include '5h', '1d', '10w'. Does not support months.

    Returns:
        timedelta: A timedelta matching the duration given.
    
    Raises:
        ValueError: If the string is empty or incorrect.
    """
    if not timeframe: 
        raise ValueError("Timeframe cannot be empty")
    if len(timeframe) > 3:
        raise ValueError("Timeframe cannot be more than 3 characters")
    
    unit = timeframe[-1]
    amount_str = timeframe[:-1]
    
    try:
        amount = int(amount_str)
    except ValueError:
        raise ValueError("Timeframe amount must be an integer")
    
    if amount < 0:
        raise ValueError("Timeframe must be positive")
    
    if unit == 'h':
        return timedelta(hours=amount)
    elif unit == 'd':
        return timedelta(days=amount)
    elif unit == 'w':
        return timedelta(weeks=amount)
    else:
        raise ValueError("Unkown unit. Use 'h', 'd' or 'w'.")

def convert_unix_to_datetime_utc(unix_utc: Optional[float]) -> Optional[datetime]:
    """Convert UNIX timestamp to UTC datetime, or None if missing."""
    return datetime.fromtimestamp(unix_utc, tz=timezone.utc) if unix_utc is not None else None 

def get_active_tickers(connection_pool, start_time: datetime, end_time: datetime, min_mentions: int = 10) -> list[str]:
        """Get list of tickers with activity in the time period.
        
        Args:
            connection_pool: The connection pool.
            start_time: Start of time range.
            end_time: End of time range.
            min_mentions: Minimum mentions to be considered active.
            
        Returns:
            List of ticker symbols
        """
        conn = connection_pool.getconn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT ticker, SUM(mention_count) as total
                FROM mentions
                WHERE timestamp BETWEEN %s AND %s
                GROUP BY ticker
                HAVING SUM(mention_count) >= %s
                ORDER BY total DESC
            """, (start_time, end_time, min_mentions))
            
            tickers = [row[0] for row in cursor.fetchall()]
            return tickers
            
        finally:
            cursor.close()
            connection_pool.putconn(conn)