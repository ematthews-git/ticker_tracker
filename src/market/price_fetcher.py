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
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

from logging_setup import configure_logging
import logging
configure_logging()

from config import DB_URL, VALID
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import execute_batch
from utils import helper
import pandas as pd

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
            current_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
 
        logger.info(f"Collecting prices for {current_time}")

        # Get all active tickers from the last 24 hours
        start_time = current_time - timedelta(hours=24)
        
        active_tickers = helper.get_active_tickers(
            self.connection_pool,
            start_time, 
            current_time,
            min_mentions=2  # Lower threshold for price collection
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
                logger.info(f"Filtered out {invalid_count} invalid tickers (not in valid_tickers.json)")
            active_tickers = valid_tickers

        if not active_tickers:
            logger.warning("No valid tickers to fetch prices for after filtering")
            return

        # Fetch and store prices for all active tickers
        # Fetch 24 hours of data to ensure we have the current hour
        self.fetch_and_store_prices(active_tickers, hours_back=24)
        logger.info(f"Price collection complete for {current_time}")

    def _fetch_hourly_prices(self, tickers: list[str], hours_back: int = 24) -> dict[str, any]:
        """
        Fetch hourly price data for multiple tickers.
        
        Args:
            tickers: List of ticker symbols
            hours_back: How many hours of data to fetch (max 730 hours/~30 days)
            
        Returns:
            Dict mapping ticker to DataFrame with OHLCV data
        """
        if not tickers:
            return {}
            
        logger.info(f"Fetching hourly prices for {len(tickers)} tickers")
        
        # Convert hours to days for yfinance period parameter
        # yfinance accepts: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
        # For hourly data, we need at least 1 day, round up to ensure we get enough data
        days_needed = max(1, (hours_back + 23) // 24)  # Round up
        if days_needed <= 5:
            period = f"{days_needed}d"
        elif days_needed <= 30:
            period = "1mo"
        else:
            period = "3mo"
        
        # Calculate cutoff time to filter data
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        results = {}
        failed = []
        failure_reasons = {}  # Track why each ticker failed
        
        batch_size = 10
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i+batch_size]
            ticker_str = " ".join(batch)
            
            try:
                # Fetch data for batch
                data = yf.download(
                    ticker_str,
                    period=period,
                    interval="1h",
                    group_by='ticker',
                    auto_adjust=True,  # Adjusts for splits/dividends
                    threads=False,  # Disable threading to avoid thread start issues
                    progress=False
                )
                
                # Parse results and filter to only include needed hours
                if len(batch) == 1:
                    # Single ticker returns different structure
                    ticker = batch[0]
                    if not data.empty:
                        # Filter to only include data after cutoff_time
                        # Handle timezone-aware and timezone-naive indices
                        filtered_data = self._filter_by_time(data, cutoff_time)
                        if not filtered_data.empty:
                            results[ticker] = filtered_data
                        else:
                            failed.append(ticker)
                            failure_reasons[ticker] = "No data after filtering to cutoff time"
                    else:
                        failed.append(ticker)
                        failure_reasons[ticker] = "Empty data returned from yfinance"
                else:
                    # Multiple tickers
                    for ticker in batch:
                        try:
                            ticker_data = data[ticker]
                            if not ticker_data.empty:
                                # Filter to only include data after cutoff_time
                                filtered_data = self._filter_by_time(ticker_data, cutoff_time)
                                if not filtered_data.empty:
                                    results[ticker] = filtered_data
                                else:
                                    failed.append(ticker)
                                    failure_reasons[ticker] = "No data after filtering to cutoff time"
                            else:
                                failed.append(ticker)
                                failure_reasons[ticker] = "Empty data returned from yfinance"
                        except KeyError:
                            failed.append(ticker)
                            failure_reasons[ticker] = "Ticker not found in batch response (KeyError)"
                            
                # Rate limiting - be nice to Yahoo
                time.sleep(0.5)
                
            except Exception as e:
                logger.debug(f"Error fetching batch {batch}: {e}")
                # Mark all in batch as failed, but try individually as fallback
                for ticker in batch:
                    if ticker not in results:
                        failed.append(ticker)
                        failure_reasons[ticker] = f"Batch error: {str(e)[:50]}"
        
        # Try fetching failed tickers individually as fallback
        if failed:
            logger.info(f"Attempting to fetch {len(failed)} failed tickers individually...")
            individual_failed = []
            for ticker in failed[:]:  # Copy list to iterate safely
                try:
                    # Try fetching individually
                    individual_data = yf.download(
                        ticker,
                        period=period,
                        interval="1h",
                        auto_adjust=True,
                        threads=False,
                        progress=False
                    )
                    
                    if not individual_data.empty:
                        filtered_data = self._filter_by_time(individual_data, cutoff_time)
                        if not filtered_data.empty:
                            results[ticker] = filtered_data
                            failed.remove(ticker)
                            failure_reasons.pop(ticker, None)
                            logger.debug(f"Successfully fetched {ticker} individually")
                            continue
                    
                    # Still failed
                    if ticker not in failure_reasons:
                        failure_reasons[ticker] = "No hourly data available (empty after individual fetch)"
                    individual_failed.append(ticker)
                    
                except Exception as e:
                    if ticker not in failure_reasons:
                        failure_reasons[ticker] = f"Individual fetch error: {str(e)[:50]}"
                    individual_failed.append(ticker)
                
                # Rate limiting for individual fetches
                time.sleep(0.3)
        
        # Log summary of failures
        if failed:
            logger.warning(f"Failed to fetch data for {len(failed)} tickers")
            # Log top failure reasons
            reason_counts = {}
            for ticker, reason in failure_reasons.items():
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            
            logger.info("Failure reasons:")
            for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                logger.info(f"  {reason}: {count} tickers")
            
            # Log some example failed tickers
            logger.debug(f"Example failed tickers: {failed[:20]}")
            
        logger.info(f"Successfully fetched data for {len(results)}/{len(tickers)} tickers")
        return results
    
    def _filter_by_time(self, data: pd.DataFrame, cutoff_time: datetime) -> pd.DataFrame:
        """Filter DataFrame to only include rows after cutoff_time.
        
        Handles both timezone-aware and timezone-naive indices.
        
        Args:
            data: DataFrame with datetime index
            cutoff_time: UTC datetime to filter from
            
        Returns:
            Filtered DataFrame
        """
        if data.empty:
            return data
        
        # Make a copy to avoid modifying original
        filtered = data.copy()
        
        # Convert index to timezone-aware UTC if needed
        if filtered.index.tz is None:
            # Assume timezone-naive indices are in UTC (yfinance typically returns UTC)
            filtered.index = filtered.index.tz_localize(timezone.utc)
        else:
            # Convert to UTC if in different timezone
            filtered.index = filtered.index.tz_convert(timezone.utc)
        
        # Filter to only include data after cutoff_time
        mask = filtered.index >= cutoff_time
        return filtered[mask]
    
    def save_prices_to_db(self, ticker: str, price_data) -> None:
        """Save price data to database"""
        if not self.connection_pool:
            raise ValueError("Connection pool required")
            
        if price_data.empty:
            logger.warning(f"No price data to save for {ticker}")
            return
            
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        
        try:
            # Prepare data for insertion
            # Use itertuples() instead of iterrows() for better performance and to avoid Series ambiguity
            data = []
            skipped_count = 0
            
            # Ensure we have the expected columns (handle MultiIndex if present)
            if isinstance(price_data.columns, pd.MultiIndex):
                # Flatten MultiIndex columns
                price_data.columns = price_data.columns.get_level_values(-1)
            
            for timestamp, row in price_data.iterrows():
                try:
                    # Get scalar values - use .item() if it's a Series, otherwise use directly
                    def get_scalar(value):
                        if isinstance(value, pd.Series):
                            return value.item() if len(value) == 1 else value.iloc[0]
                        return value
                    
                    open_val = get_scalar(row.get('Open', row.iloc[0] if len(row) > 0 else None))
                    high_val = get_scalar(row.get('High', row.iloc[1] if len(row) > 1 else None))
                    low_val = get_scalar(row.get('Low', row.iloc[2] if len(row) > 2 else None))
                    close_val = get_scalar(row.get('Close', row.iloc[3] if len(row) > 3 else None))
                    volume_val = get_scalar(row.get('Volume', row.iloc[4] if len(row) > 4 else None))
                    
                    # Skip rows with NaN values in critical fields
                    if (pd.isna(open_val) or pd.isna(high_val) or 
                        pd.isna(low_val) or pd.isna(close_val)):
                        skipped_count += 1
                        continue
                    
                    # Convert pandas Timestamp to Python datetime
                    dt = timestamp.to_pydatetime()
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    
                    # Round timestamp to the hour (:00) to ensure consistency
                    dt = dt.replace(minute=0, second=0, microsecond=0)
                    
                    # Handle NaN volume (convert to 0)
                    if pd.isna(volume_val):
                        volume = 0
                    else:
                        volume = int(volume_val)
                    
                    data.append((
                        ticker.upper(),
                        dt,
                        float(open_val),
                        float(high_val),
                        float(low_val),
                        float(close_val),
                        volume
                    ))
                except Exception as e:
                    logger.debug(f"Error processing row for {ticker} at {timestamp}: {e}")
                    skipped_count += 1
                    continue
            
            # Log skipped rows once if any were skipped
            if skipped_count > 0:
                logger.debug(f"Skipped {skipped_count} rows with NaN price values for {ticker}")
            
            execute_batch(cursor, """
                INSERT INTO stock_prices (ticker, timestamp, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, timestamp) 
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
            """, data)
            
            conn.commit()
            logger.debug(f"Saved {len(data)} price records for {ticker}")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving prices for {ticker}: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
    
    def fetch_and_store_prices(self, tickers: list[str], hours_back: int = 24) -> None:
        """Convenience method to fetch and store in one call"""
        price_data = self._fetch_hourly_prices(tickers, hours_back)
        
        for ticker, data in price_data.items():
            try:
                self.save_prices_to_db(ticker, data)
            except Exception as e:
                logger.error(f"Failed to save {ticker}: {e}", exc_info=True)
    
    def _process_single_hour(self, timestamp: datetime) -> tuple[bool, str]:
        """Process prices for a single hour.
        
        Args:
            timestamp: The hour to process
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            self.collect_and_store_prices(timestamp)
            return True, f"Processed {timestamp}"
        except Exception as e:
            return False, f"Error processing {timestamp}: {e}"
    
    def _get_hours_to_process(self, days: int, skip_existing: bool = True) -> List[datetime]:
        """Get list of hours that need processing.
        
        Args:
            days: Number of days to check
            skip_existing: If True, skip hours that already have prices for active tickers
            
        Returns:
            List of timestamps that need processing
        """
        current = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        total_hours = days * 24
        hours_to_process = []
        
        logger.info(f"Scanning {total_hours} hours to find what needs processing...")
        
        # Build list of timestamps to check (newest to oldest)
        timestamps_to_check = [
            current - timedelta(hours=hours_ago) 
            for hours_ago in range(total_hours)
        ]
        
        # Batch check which timestamps already have prices
        existing_timestamps = set()
        if skip_existing:
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            try:
                # Get min and max timestamps to check
                min_ts = timestamps_to_check[-1]
                max_ts = timestamps_to_check[0]
                
                cursor.execute("""
                    SELECT DISTINCT timestamp 
                    FROM stock_prices
                    WHERE timestamp >= %s AND timestamp <= %s
                """, (min_ts, max_ts))
                existing_timestamps = {row[0] for row in cursor.fetchall()}
            finally:
                cursor.close()
                self.connection_pool.putconn(conn)
        
        # Check which hours have active tickers (mentions data)
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        try:
            # Get all hours that have mentions data
            min_ts = timestamps_to_check[-1] - timedelta(hours=24)  # +24 for lookback window
            max_ts = timestamps_to_check[0]
            
            cursor.execute("""
                SELECT DISTINCT DATE_TRUNC('hour', timestamp)::timestamptz as hour
                FROM mentions
                WHERE timestamp >= %s
                AND timestamp <= %s
            """, (min_ts, max_ts))
            hours_with_mentions = {row[0] for row in cursor.fetchall()}
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
        
        # Filter to only hours that need processing (newest to oldest)
        for timestamp in timestamps_to_check:
            if skip_existing and timestamp in existing_timestamps:
                # Check if we have prices for this hour - if yes, skip
                continue
            
            # Check if this hour has mentions data (check the 24h window)
            window_start = timestamp - timedelta(hours=24)
            window_end = timestamp
            
            # Check if any hour in the mentions set falls within our window
            has_mentions = any(
                window_start <= hour <= window_end 
                for hour in hours_with_mentions
            )
            
            if not has_mentions:
                # Stop when we hit data without mentions (processing newest to oldest)
                logger.info(f"No mentions data found for {timestamp}. Stopping scan.")
                break
            
            hours_to_process.append(timestamp)
        
        return hours_to_process
    
    def backfill_prices(self, days: int = 7, skip_existing: bool = True, max_workers: int = 4) -> None:
        """Backfill prices for the specified number of days.
        
        Processes hours in parallel for maximum speed. Stops when mentions data is no longer available.
        
        Args:
            days: Number of days to backfill (default: 7)
            skip_existing: If True, skip hours that already have prices (default: True)
            max_workers: Number of parallel workers (default: 4)
        """
        logger.info(f"Starting optimized backfill for last {days} days")
        
        # Get list of hours that need processing (batch checks upfront)
        hours_to_process = self._get_hours_to_process(days, skip_existing)
        
        if not hours_to_process:
            logger.info("No hours need processing - all prices are up to date!")
            return
        
        total_hours = len(hours_to_process)
        logger.info(f"Found {total_hours} hours to process. Processing in parallel with {max_workers} workers...")
        
        processed = 0
        failed = 0
        
        # Process hours in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_timestamp = {
                executor.submit(self._process_single_hour, timestamp): timestamp
                for timestamp in hours_to_process
            }
            
            # Process results as they complete
            for future in as_completed(future_to_timestamp):
                timestamp = future_to_timestamp[future]
                try:
                    success, message = future.result()
                    if success:
                        processed += 1
                        if processed % 10 == 0:
                            logger.info(f"Progress: {processed}/{total_hours} hours processed")
                    else:
                        failed += 1
                        logger.error(message)
                except Exception as e:
                    failed += 1
                    logger.error(f"Unexpected error processing {timestamp}: {e}", exc_info=True)
        
        logger.info(f"Backfill complete: {processed} hours processed, {failed} failed")


def main():
    """Main function to run price collection."""
    logger.info("Price Collector Started")
    
    # Create connection pool
    pool = SimpleConnectionPool(
        minconn=1,
        maxconn=5,
        dsn=DB_URL
    )
    
    collector = PriceCollector(pool)
    
    print("=" * 60)
    print("Reddit Ticker Price Collector")
    print("=" * 60)
    print("\nOptions:")
    print("1. Collect prices for current hour")
    print("2. Backfill prices for last 7 days")
    print("3. Run continuous collection (hourly)")
    print("9. Exit")
    print("=" * 60)
    
    choice = input("\nEnter choice: ").strip()
    
    if choice == "1":
        logger.info("Collecting current prices...")
        collector.collect_and_store_prices()
        logger.info("Price collection complete")
        
    elif choice == "2":
        logger.info("Backfilling prices for last 7 days...")
        collector.backfill_prices(days=7, skip_existing=True)
    
    elif choice == "3":
        import schedule
        
        logger.info("Starting continuous price collection (hourly)")
        print("\nCollecting prices every hour on the hour (:00)")
        print("Press Ctrl+C to stop\n")
        
        # Collect now
        collector.collect_and_store_prices()
        
        # Schedule hourly collection
        schedule.every().hour.at(":00").do(collector.collect_and_store_prices)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("\nPrice collector stopped by user")
    
    elif choice == "9":
        logger.info("Exiting")
    
    else:
        logger.warning(f"Invalid choice: {choice}")
    
    # Close pool
    pool.closeall()


if __name__ == "__main__":
    main()
