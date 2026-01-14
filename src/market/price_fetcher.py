import yfinance as yf
from datetime import datetime, timedelta, timezone
from utils import helper

from logging_setup import configure_logging
import logging
configure_logging()

from config import DB_URL

logger = logging.getLogger(__name__)

class PriceCollector:
    """Collects and stores stock prices for relevant tickers"""
    def __init__(self, connection_pool):
         self.connection_pool = connection_pool
    
    def collect_and_store_prices(self, current_time: datetime = None) -> None:
         
        if current_time is None:
            current_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        logger.info(f"Collecting prices for {current_time}")

        #get all active tickers from the last 24 hours
        from datetime import timedelta
        start_time = current_time - timedelta(hours=24)
        
        active_tickers = helper.get_active_tickers(
            self.connection_pool,
            start_time, 
            current_time,
            min_mentions=2  
        )

        logger.info(f"Found {len(active_tickers)} active tickers")


