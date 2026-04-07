"""
Statistics Collection Script

This script periodically calculates and stores statistical features for all active tickers.
Run this alongside your main data collection to build up historical statistics.

Usage:
    python statistics_collector.py
"""

from logging_setup import configure_logging
import logging
configure_logging()

from datetime import datetime, timezone
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import execute_batch
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import DB_URL
from analysis.statistical_analyser import StatisticalAnalyser
from models import TickerStats
from utils import helper

logger = logging.getLogger(__name__)


class StatisticsCollector:
    """Collects and stores statistical features for tickers."""
    
    def __init__(self, connection_pool):
        self.connection_pool = connection_pool
        self.analyser = StatisticalAnalyser(connection_pool)
    
    def collect_and_store_statistics(self, current_time: datetime = None) -> None:
        """Calculate statistics for all active tickers and store in database.
        
        Args:
            current_time: Time to calculate statistics for (defaults to now)
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        
        logger.info(f"Collecting statistics for {current_time}")
        
        # Get all active tickers from the last 24 hours
        from datetime import timedelta
        start_time = current_time - timedelta(hours=24)
        
        active_tickers = helper.get_active_tickers(
            self.connection_pool,
            start_time, 
            current_time,
            min_mentions=5  # Lower threshold for statistics collection
        )
        
        logger.info(f"Found {len(active_tickers)} active tickers")
        
        # Calculate statistics for each ticker
        statistics_batch: List[TickerStats] = []
        
        for ticker in active_tickers:
            try:
                # Get comprehensive statistics - this does all the calculation internally
                stats = self.analyser.get_ticker_statistics_summary(ticker, current_time)
                statistics_batch.append(stats)
                
                logger.debug(f"Collected stats for {ticker}: Z={stats.mention_zscore}, V={stats.mention_velocity}")
                
            except Exception as e:
                logger.error(f"Error collecting stats for {ticker}: {e}", exc_info=True)
                continue
        
        # Batch insert to database
        if statistics_batch:
            self._batch_insert_statistics(statistics_batch)
            logger.info(f"Stored statistics for {len(statistics_batch)} tickers")
        else:
            logger.warning("No statistics to store")
    
    def _batch_insert_statistics(self, statistics_batch: List[TickerStats]) -> None:
        """Batch insert statistics into database.
        
        Args:
            statistics_batch: List of TickerStats objects
        """
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        
        try:
            # Convert TickerStats objects to tuples for batch insert
            data = [
                (
                    stats.ticker,
                    stats.timestamp,
                    stats.mention_count,
                    stats.mention_zscore,
                    stats.mention_velocity,
                    stats.avg_sentiment,
                    stats.sentiment_zscore,
                    stats.unique_users,
                    stats.total_score,
                    stats.total_comments,
                    stats.subreddit_diversity,
                    stats.spike_detected
                )
                for stats in statistics_batch
            ]
            
            execute_batch(cursor, """
                INSERT INTO ticker_statistics (
                    ticker, timestamp, mention_count, mention_zscore, mention_velocity,
                    avg_sentiment, sentiment_zscore, unique_users, total_score, 
                    total_comments, subreddit_diversity, spike_detected
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, timestamp) 
                DO UPDATE SET
                    mention_count = EXCLUDED.mention_count,
                    mention_zscore = EXCLUDED.mention_zscore,
                    mention_velocity = EXCLUDED.mention_velocity,
                    avg_sentiment = EXCLUDED.avg_sentiment,
                    sentiment_zscore = EXCLUDED.sentiment_zscore,
                    unique_users = EXCLUDED.unique_users,
                    total_score = EXCLUDED.total_score,
                    total_comments = EXCLUDED.total_comments,
                    subreddit_diversity = EXCLUDED.subreddit_diversity,
                    spike_detected = EXCLUDED.spike_detected
            """, data)
            
            conn.commit()
            logger.info(f"Successfully inserted {len(statistics_batch)} statistics records")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error batch inserting statistics: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
    
    def find_anomalous_tickers_now(self) -> List[TickerStats]:
        """Find currently anomalous tickers and log them.
        
        Returns:
            List[TickerStats]: Anomalous tickers with their statistics
        """
        current_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        
        anomalous = self.analyser.identify_anomalous_tickers(
            current_time,
            mention_zscore_threshold=2.0,
            sentiment_zscore_threshold=1.5,
            velocity_threshold=5.0,
            min_mentions=10
        )
        
        if anomalous:
            logger.info(f"\n{'='*60}")
            logger.info(f"ANOMALOUS TICKERS DETECTED: {len(anomalous)}")
            logger.info(f"{'='*60}")
            
            for i, stats in enumerate(anomalous[:10], 1):  # Top 10
                logger.info(f"\n{i}. {stats.ticker}")
                logger.info(f"   Mention Z-Score: {stats.mention_zscore}")
                logger.info(f"   Sentiment Z-Score: {stats.sentiment_zscore}")
                logger.info(f"   Velocity: {stats.mention_velocity} mentions/hour")
                logger.info(f"   Diversity: {stats.subreddit_diversity} subreddits")
                logger.info(f"   Total Mentions: {stats.mention_count}")
                logger.info(f"   Avg Sentiment: {stats.avg_sentiment}")
                
                # Show why it's anomalous
                reasons = stats.get_anomaly_reasons()
                if reasons:
                    logger.info(f"   Reasons: {', '.join(reasons)}")
        else:
            logger.info("No anomalous tickers detected")
        
        return anomalous
    
    def _has_sentiment_data(self, timestamp: datetime) -> bool:
        """Check if there are any mentions with sentiment scores for a given hour.
        
        Since avg_sentiment is NOT NULL in the schema, we check for non-zero sentiment
        values, which indicates sentiment was actually calculated (vs. default 0 values).
        
        Args:
            timestamp: The hour to check
            
        Returns:
            bool: True if there are mentions with non-zero sentiment scores
        """
        from datetime import timedelta
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        
        try:
            # Check if there are any mentions with non-zero sentiment in the 24-hour window
            # This indicates sentiment was actually calculated (not just default 0)
            start_time = timestamp - timedelta(hours=24)
            end_time = timestamp
            
            cursor.execute("""
                SELECT COUNT(*) 
                FROM mentions
                WHERE timestamp BETWEEN %s AND %s
                AND avg_sentiment != 0
            """, (start_time, end_time))
            
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
    
    def _statistics_exist(self, timestamp: datetime) -> bool:
        """Check if statistics already exist for a given timestamp.
        
        Args:
            timestamp: The hour to check
            
        Returns:
            bool: True if statistics already exist
        """
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM ticker_statistics
                WHERE timestamp = %s
            """, (timestamp,))
            
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
    
    def _process_single_hour(self, timestamp: datetime) -> tuple[bool, str]:
        """Process statistics for a single hour.
        
        Args:
            timestamp: The hour to process
            
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            self.collect_and_store_statistics(timestamp)
            return True, f"Processed {timestamp}"
        except Exception as e:
            return False, f"Error processing {timestamp}: {e}"
    
    def _get_hours_to_process(self, days: int, skip_existing: bool = True) -> List[datetime]:
        """Get list of hours that need processing.
        
        Args:
            days: Number of days to check
            skip_existing: If True, skip hours that already have statistics
            
        Returns:
            List of timestamps that need processing
        """
        from datetime import timedelta
        
        current = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        total_hours = days * 24
        hours_to_process = []
        
        logger.info(f"Scanning {total_hours} hours to find what needs processing...")
        
        # Build list of timestamps to check (newest to oldest)
        timestamps_to_check = [
            current - timedelta(hours=hours_ago) 
            for hours_ago in range(total_hours)
        ]
        
        # Batch check which timestamps already have statistics
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
                    FROM ticker_statistics
                    WHERE timestamp >= %s AND timestamp <= %s
                """, (min_ts, max_ts))
                existing_timestamps = {row[0] for row in cursor.fetchall()}
            finally:
                cursor.close()
                self.connection_pool.putconn(conn)
        
        # Batch check which hours have sentiment data
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        try:
            # Get all hours that have sentiment data
            min_ts = timestamps_to_check[-1] - timedelta(hours=24)  # +24 for lookback window
            max_ts = timestamps_to_check[0]
            
            cursor.execute("""
                SELECT DISTINCT DATE_TRUNC('hour', timestamp)::timestamptz as hour
                FROM mentions
                WHERE timestamp >= %s
                AND timestamp <= %s
                AND avg_sentiment != 0
            """, (min_ts, max_ts))
            hours_with_sentiment = {row[0] for row in cursor.fetchall()}
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
        
        # Filter to only hours that need processing (newest to oldest)
        for timestamp in timestamps_to_check:
            if skip_existing and timestamp in existing_timestamps:
                continue
            
            # Check if this hour has sentiment data (check the 24h window)
            window_start = timestamp - timedelta(hours=24)
            window_end = timestamp
            
            # Check if any hour in the sentiment set falls within our window
            has_sentiment = any(
                window_start <= hour <= window_end 
                for hour in hours_with_sentiment
            )
            
            if not has_sentiment:
                # Stop when we hit data without sentiment (processing newest to oldest)
                logger.info(f"No sentiment data found for {timestamp}. Stopping scan.")
                break
            
            hours_to_process.append(timestamp)
        
        return hours_to_process
    
    def backfill_statistics(self, days: int = 7, skip_existing: bool = True, max_workers: int = 4) -> None:
        """Backfill statistics for the specified number of days.
        
        Processes hours in parallel for maximum speed. Stops when sentiment data is no longer available.
        
        Args:
            days: Number of days to backfill (default: 7)
            skip_existing: If True, skip hours that already have statistics (default: True)
            max_workers: Number of parallel workers (default: 4)
        """
        logger.info(f"Starting optimized backfill for last {days} days")
        
        # Get list of hours that need processing (batch checks upfront)
        hours_to_process = self._get_hours_to_process(days, skip_existing)
        
        if not hours_to_process:
            logger.info("No hours need processing - all statistics are up to date!")
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
    """Main function to run statistics collection."""
    logger.info("Statistics Collector Started")
    
    # Create connection pool
    pool = SimpleConnectionPool(
        minconn=1,
        maxconn=15,
        dsn=DB_URL
    )
    
    collector = StatisticsCollector(pool)
    
    print("=" * 60)
    print("Reddit Ticker Statistics Collector")
    print("=" * 60)
    print("\nOptions:")
    print("1. Collect statistics for current hour")
    print("2. Find anomalous tickers now")
    print("3. Backfill statistics for last 7 days")
    print("4. Run continuous collection (hourly)")
    print("9. Exit")
    print("=" * 60)
    
    choice = input("\nEnter choice: ").strip()
    
    if choice == "1":
        logger.info("Collecting current statistics...")
        collector.collect_and_store_statistics()
        logger.info("Statistics collection complete")
        
    elif choice == "2":
        logger.info("Finding anomalous tickers...")
        anomalous = collector.find_anomalous_tickers_now()
        
        if anomalous:
            print(f"\nFound {len(anomalous)} anomalous tickers:")
            print("\n" + "=" * 90)
            print(f"{'Ticker':<8} {'MentionZ':<10} {'SentZ':<10} {'Velocity':<10} {'Diversity':<10} {'Mentions':<10}")
            print("=" * 90)
            
            for stats in anomalous[:20]:
                print(f"{stats.ticker:<8} "
                      f"{stats.mention_zscore or 'N/A':<10} "
                      f"{stats.sentiment_zscore or 'N/A':<10} "
                      f"{stats.mention_velocity:<10.2f} "
                      f"{stats.subreddit_diversity:<10} "
                      f"{stats.mention_count:<10}")
        else:
            print("\nNo anomalous tickers found")
    
    elif choice == "3":
        logger.info("Backfilling statistics for last 7 days...")
        collector.backfill_statistics(days=7, skip_existing=True)
    
    elif choice == "4":
        import schedule
        import time
        
        logger.info("Starting continuous statistics collection (hourly)")
        print("\nCollecting statistics every hour at :30")
        print("Press Ctrl+C to stop\n")
        
        # Collect now
        collector.collect_and_store_statistics()
        
        # Schedule hourly collection
        schedule.every().hour.at(":30").do(collector.collect_and_store_statistics)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("\nStatistics collector stopped by user")
    
    elif choice == "9":
        logger.info("Exiting")
    
    else:
        logger.warning(f"Invalid choice: {choice}")
    
    # Close pool
    pool.closeall()


if __name__ == "__main__":
    main()