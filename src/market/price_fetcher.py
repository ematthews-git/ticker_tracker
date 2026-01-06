import yfinance as yf

from logging_setup import configure_logging
import logging
configure_logging()

from config import DB_URL

logger = logging.getLogger(__name__)

class PriceCollector:
    """Collects and stores stock prices for relevant tickers"""
    def __init__(self, connection_pool):
         self.connection_pool = connection_pool
         