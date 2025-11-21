from datetime import datetime, timedelta, timezone


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

        