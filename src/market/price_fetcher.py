"""
Price Collection Script

This script periodically fetches and stores stock prices for all active tickers.
Run this alongside your main data collection to build up historical price data.

Usage:
    python price_fetcher.py
"""

import yfinance as yf
from datetime import datetime, timedelta, timezone
import time
from typing import Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import DB_URL, VALID
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import execute_batch
from utils import helper
import pandas as pd

from logging_setup import configure_logging
import logging

configure_logging()


logger = logging.getLogger(__name__)


class PriceCollector:
    """Collects and stores stock prices for relevant tickers"""

    def __init__(self, connection_pool):
        self.connection_pool = connection_pool

    def collect_and_store_prices(self, current_time: datetime = None) -> None:
        """Calculate prices for all active tickers and store in database.

        Args:
            current_time: Time to collect prices for (defaults to now)
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )

        logger.info(f"Collecting prices for {current_time}")

        # Get all active tickers from the last 24 hours
        start_time = current_time - timedelta(hours=24)

        active_tickers = helper.get_active_tickers(
            self.connection_pool,
            start_time,
            current_time,
            min_mentions=2,  # Lower threshold for price collection
        )

        logger.info(f"Found {len(active_tickers)} active tickers")

        if not active_tickers:
            logger.warning("No active tickers to fetch prices for")
            return

        # Filter to only valid tickers (if VALID list exists)
        if VALID:
            valid_tickers = [t for t in active_tickers if t.upper() in VALID]
            invalid_count = len(active_tickers) - len(valid_tickers)
            if invalid_count > 0:
                logger.info(f"Filtered out {invalid_count} invalid tickers")
            active_tickers = valid_tickers

        if not active_tickers:
            logger.warning("No valid tickers to fetch prices for after filtering")
            return

        # Fetch and store prices for all active tickers
        # Fetch 5 days of data to ensure we cover weekends/holidays
        self.fetch_and_store_prices(active_tickers, days_back=5)
        logger.info(f"Price collection complete for {current_time}")

    def _fetch_hourly_prices(
        self, tickers: list[str], days_back: int = 5
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch hourly price data for multiple tickers.

        Args:
            tickers: List of ticker symbols
            days_back: How many days of data to fetch (default 5 to cover weekends)

        Returns:
            Dict mapping ticker to DataFrame with OHLCV data
        """
        if not tickers:
            return {}

        logger.info(
            f"Fetching hourly prices for {len(tickers)} tickers (last {days_back} days)"
        )

        period = f"{days_back}d"
        if days_back > 5:
            period = "1mo"

        results = {}
        failed = []

        # Process in smaller chunks to avoid overwhelming yfinance or getting large responses
        chunk_size = 20
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i : i + chunk_size]
            ticker_str = " ".join(chunk)

            try:
                # Fetch data for chunk
                data = yf.download(
                    ticker_str,
                    period=period,
                    interval="1h",
                    group_by="ticker",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                )

                if len(chunk) == 1:
                    ticker = chunk[0]
                    if not data.empty:
                        results[ticker] = data
                    else:
                        failed.append(ticker)
                else:
                    for ticker in chunk:
                        try:
                            ticker_data = data[ticker]
                            # Check if we have actual data (not all NaNs)
                            if (
                                not ticker_data.empty
                                and not ticker_data.isna().all().all()
                            ):
                                results[ticker] = ticker_data
                            else:
                                failed.append(ticker)
                        except KeyError:
                            failed.append(ticker)

                # Rate limiting
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error fetching chunk {chunk}: {e}")
                failed.extend(chunk)

        if failed:
            logger.warning(
                f"Failed to fetch data for {len(failed)} tickers: {failed[:10]}..."
            )

        logger.info(
            f"Successfully fetched data for {len(results)}/{len(tickers)} tickers"
        )
        return results

    def save_prices_to_db(self, ticker: str, price_data: pd.DataFrame) -> None:
        """Save price data to database"""
        if not self.connection_pool:
            raise ValueError("Connection pool required")

        if price_data.empty:
            return

        conn = self.connection_pool.getconn()
        cursor = conn.cursor()

        try:
            data = []

            # Ensure we have the expected columns
            if isinstance(price_data.columns, pd.MultiIndex):
                price_data.columns = price_data.columns.get_level_values(-1)

            for timestamp, row in price_data.iterrows():
                try:
                    # Skip if any required value is NaN
                    if row[["Open", "High", "Low", "Close"]].isna().any():
                        continue

                    dt = timestamp.to_pydatetime()
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)

                    # Round to hour
                    dt = dt.replace(minute=0, second=0, microsecond=0)

                    volume = (
                        0
                        if pd.isna(row.get("Volume", 0))
                        else int(row.get("Volume", 0))
                    )

                    data.append(
                        (
                            ticker.upper(),
                            dt,
                            float(row["Open"]),
                            float(row["High"]),
                            float(row["Low"]),
                            float(row["Close"]),
                            volume,
                        )
                    )
                except Exception as e:
                    logger.debug(f"Skipping row for {ticker} at {timestamp}: {e}")
                    continue

            if not data:
                return

            execute_batch(
                cursor,
                """
                INSERT INTO stock_prices (ticker, timestamp, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, timestamp)
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
            """,
                data,
            )

            conn.commit()
            logger.debug(f"Saved {len(data)} price records for {ticker}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving prices for {ticker}: {e}")
            raise
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)

    def fetch_and_store_prices(self, tickers: list[str], days_back: int = 5) -> None:
        """Convenience method to fetch and store in one call"""
        price_data = self._fetch_hourly_prices(tickers, days_back)

        for ticker, data in price_data.items():
            try:
                self.save_prices_to_db(ticker, data)
            except Exception as e:
                logger.error(f"Failed to save {ticker}: {e}")

    def backfill_prices(self, days: int = 7) -> None:
        """Simple backfill for active tickers"""
        logger.info(f"Starting backfill for last {days} days")

        # Just run the standard collection but with a wider window for active tickers
        current_time = datetime.now(timezone.utc)
        start_time = current_time - timedelta(days=days)

        active_tickers = helper.get_active_tickers(
            self.connection_pool, start_time, current_time, min_mentions=1
        )

        if active_tickers:
            logger.info(f"Backfilling for {len(active_tickers)} tickers")
            self.fetch_and_store_prices(active_tickers, days_back=days)
        else:
            logger.info("No active tickers found for backfill")


def main():
    """Main function to run price collection."""
    logger.info("Price Collector Started")

    pool = SimpleConnectionPool(minconn=1, maxconn=5, dsn=DB_URL)
    collector = PriceCollector(pool)

    print("=" * 60)
    print("Reddit Ticker Price Collector")
    print("=" * 60)
    print("1. Collect prices (last 5 days)")
    print("2. Backfill prices (last 30 days)")
    print("3. Run continuous collection (hourly)")
    print("9. Exit")
    print("=" * 60)

    choice = input("\nEnter choice: ").strip()

    if choice == "1":
        collector.collect_and_store_prices()
    elif choice == "2":
        collector.backfill_prices(days=30)
    elif choice == "3":
        import schedule

        logger.info("Starting continuous price collection")
        collector.collect_and_store_prices()
        schedule.every().hour.at(":00").do(collector.collect_and_store_prices)
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Stopped by user")
    elif choice == "9":
        pass
    else:
        print("Invalid choice")

    pool.closeall()


if __name__ == "__main__":
    main()
