import numpy as np
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional
import logging

from models import MentionDataPoint, TickerStats
from storage import database_manager

logger = logging.getLogger(__name__)

#The amount of data needed to be considered valid
DATA_SUFFICIENCY_VAL = 2

class StatisticalAnalyser:
    """Statistical analysis of data"""

    def __init__(self, connection_pool) -> None:
        self.connection_pool = connection_pool

    def calculate_mention_zscore(self, ticker: str, current_time: datetime, window_days: int = 30, aggregation_hours: int =1) -> Optional[float]:
        """Calculate the Z-score for current mention count compared to historical baseline.

        Args:
            ticker (str): Stock ticker symbol.
            current_time (datetime): The time to calculate Z for
            window_days (int, optional): Number of days of historical data to use. Defaults to 30.
            aggregation_hours (int, optional): Hours to aggregate mentions over. Defaults to 1.

        Returns:
            Optional[float]: Z score 
        """

        end_time = current_time
        start_time = current_time - timedelta(days=window_days)

        #Fetch historical data
        mentions = database_manager.fetch_ticker_mentions(self.connection_pool, ticker, start_time, end_time)

        if len(mentions) < DATA_SUFFICIENCY_VAL:
            logger.warning(f"Insufficient data for {ticker} Z-score calculation")
            return None
        
        #Aggregate by time window
        aggregated = self._aggregate_mentions_by_time(mentions, aggregation_hours)

        if len(aggregated) < 2:
            return None
        
        #Get mention counts
        mention_counts = [count for _, count in aggregated]

        #calculate stats
        mean = float(np.mean(mention_counts))
        std = float(np.std(mention_counts, ddof=1))

        if std == 0:
            logger.warning(f"Zero standard deviation for {ticker}")
            return 0.0
        
        #current val is the most recent aggregated count
        current_count = mention_counts[-1]

        #calculate z
        zscore = (current_count - mean) / std

        return round(float(zscore), 4)
    
    def calculate_sentiment_zscore(self, ticker: str, current_time: datetime, 
                                   window_days: int = 30, aggregation_hours: int = 1) -> Optional[float]:
        """Calculate Z-score for sentiment to detect unusual sentiment shifts.
        
        Args:
            ticker (str): Stock ticker symbol.
            current_time (datetime): The time point to calculate Z-score for.
            window_days (int): Number of days of historical data to use.
            aggregation_hours (int): Hours to aggregate over.
            
        Returns:
            Optional[float]: Sentiment Z-score, or None if insufficient data.
        """
        end_time = current_time
        start_time = current_time - timedelta(days=window_days)
        
        mentions = database_manager.fetch_ticker_mentions(self.connection_pool, ticker, start_time, end_time)
        
        if len(mentions) < DATA_SUFFICIENCY_VAL:
            return None
        
        # Aggregate sentiment by time window
        aggregated = self._aggregate_sentiment_by_time(mentions, hours=aggregation_hours)
        
        if len(aggregated) < DATA_SUFFICIENCY_VAL:
            return None
        
        sentiments = [sentiment for _, sentiment in aggregated]
        
        mean = float(np.mean(sentiments))
        std = float(np.std(sentiments, ddof=1))
        
        if std == 0:
            return 0.0
        
        current_sentiment = sentiments[-1]
        zscore = (current_sentiment - mean) / std
        
        return round(float(zscore), 4)
    
    def calculate_mention_velocity(self, ticker: str, current_time: datetime, lookback_hours: int = 24) -> float:
        """Calculate the rate of change in mentions (mentions / hour)

        Args:
            ticker (str): Stock ticker symbol.
            current_time (datetime): Current time point.
            lookback_hours (int, optional): Hours to lookback for calculation. Defaults to 24.

        Returns:
            float: Rate of change (mentions per hour).
        """
        end_time = current_time
        start_time = current_time - timedelta(hours=lookback_hours)

        mentions = database_manager.fetch_ticker_mentions(
            self.connection_pool,
            ticker,
            start_time,
            end_time
        )

        if len(mentions) < DATA_SUFFICIENCY_VAL: 
            return 0.0

        #Aggregate
        hourly_mentions = self._aggregate_mentions_by_time(mentions, hours=1)

        if len (hourly_mentions) < DATA_SUFFICIENCY_VAL: 
            return 0.0
        
        #Calculate linear regression slope
        times = np.array([i for i in range(len(hourly_mentions))])
        counts = np.array([count for _, count in hourly_mentions])

        #Simple linear regression: y = mx + b, where m=velocity
        if len(times) > 1:
            #Utilises method of least squares
            slope = np.polyfit(times, counts, 1)[0]
            return round(float(slope), 4)

        return 0.0
    
    def calculate_subreddit_diversity(self, ticker: str, current_time: datetime, lookback_hours: int = 24) -> int:
        """Calculate how many unique subreddits mention the ticker.
        
        Args:
            ticker (str): Stock ticker symbol.
            current_time (datetime): Current time point.
            lookback_hours (int): Hours to look back.
            
        Returns:
            int: Number of unique subreddits mentioning the ticker.
        """
        end_time = current_time
        start_time = current_time - timedelta(hours=lookback_hours)
        
        mentions = database_manager.fetch_ticker_mentions(
            self.connection_pool,
            ticker,
            start_time,
            end_time
        )
        
        unique_subreddits = set(m.subreddit for m in mentions)
        return len(unique_subreddits)
    
    def identify_anomalous_tickers(self, current_time: datetime,
                                   mention_zscore_threshold: float = 2.0, sentiment_zscore_threshold: float = 2.0,
                                   velocity_threshold: float = 5.0, min_mentions: int = 10) -> list[TickerStats]:
        """Identify tickers with anomalous activity across multiple metrics.
        
        Args:
            current_time (datetime): Current time point.
            mention_zscore_threshold (float): Minimum Z-score for mentions.
            sentiment_zscore_threshold (float): Minimum Z-score for sentiment.
            velocity_threshold (float): Minimum mention velocity (per hour).
            min_mentions (int): Minimum total mentions required.
            
        Returns:
            List[TickerStats]: List of anomalous tickers with their statistics
        """
        end_time = current_time
        start_time = current_time - timedelta(hours=24)

        tickers = self._get_active_tickers(start_time, end_time, min_mentions)

        anomalous = []
        for ticker in tickers:
            try:
                #Calculate all metrics
                mention_z = self.calculate_mention_zscore(ticker, current_time)
                sentiment_z = self.calculate_sentiment_zscore(ticker, current_time)
                velocity = self.calculate_mention_velocity(ticker, current_time)
                diversity = self.calculate_subreddit_diversity(ticker, current_time)

                #get recent mention stats
                recent_mentions = database_manager.fetch_ticker_mentions(self.connection_pool, ticker, start_time, end_time)

                total_mentions = sum(m.mention_count for m in recent_mentions)
                avg_sentiment = float(np.mean([m.avg_sentiment for m in recent_mentions]))

                #check criteria
                is_anomalous = (
                    mention_z and mention_z >= mention_zscore_threshold
                ) or (
                    sentiment_z and abs(sentiment_z) >= sentiment_zscore_threshold
                ) or (
                    velocity >= velocity_threshold
                )
                
                if is_anomalous:
                    anomalous.append(TickerStats(
                        ticker=ticker,
                        timestamp=current_time,
                        mention_count=total_mentions,
                        mention_zscore=mention_z,
                        mention_velocity=velocity,
                        avg_sentiment=round(avg_sentiment, 4),
                        sentiment_zscore=sentiment_z,
                        unique_users=sum(m.unique_users for m in recent_mentions),
                        total_score=sum(m.total_score for m in recent_mentions),
                        total_comments=sum(m.total_comments for m in recent_mentions),
                        subreddit_diversity=diversity,
                        spike_detected=False  # Will be set separately if needed
                    ))
            except Exception as e:
                logger.error(f"Error analysing {ticker}: {e}")
                continue
        
        # Sort by mention Z-score (most anomalous first)
        anomalous.sort(key=lambda x: x.mention_zscore or 0, reverse=True)
        
        return anomalous
    
    def detect_mention_spike(self, ticker: str, current_time: datetime, 
                            spike_multiplier: float = 3.0, lookback_hours: int = 4) -> tuple[bool, dict]:
        """Detect if there's a sudden spike in mentions for a ticker.

        Compares number of mentions from (current_time - lookbaack_hours) with the number of mentions
        from the same length period before then.

        Args:
            ticker (str): Stock ticker symbol.
            current_time (datetime): Current time point.
            spike_multiplier (float, optional): How many times above the baseline counts as a spike. Defaults to 3.0.
            lookback_hours (int, optional): Hours to compare. Defaults to 4.

        Returns:
            tuple[bool, dict]: is_spike, spike_details
        
        Examples:
            spike_detials = {
                ticker,
                recent_count,
                baseline_count,
                multiplier,
                is_spike,
                recent_period,
                timestamp
            }
        """
        #Recent period
        recent_end = current_time
        recent_start = current_time - timedelta(hours=lookback_hours)

        #Baseline period
        baseline_end = recent_start
        baseline_start = baseline_end - timedelta(hours=lookback_hours)

        recent_mentions = database_manager.fetch_ticker_mentions(self.connection_pool, ticker, recent_start, recent_end)
        baseline_mentions = database_manager.fetch_ticker_mentions(self.connection_pool, ticker, baseline_start, baseline_end)

        recent_count = sum(m.mention_count for m in recent_mentions)
        baseline_count = sum(m.mention_count for m in baseline_mentions)

        #Avoid division by 0
        if baseline_count == 0:
            baseline_count = 1
        
        multiplier = recent_count / baseline_count
        is_spike = multiplier >= spike_multiplier

        details = {
            'ticker': ticker,
            'recent_count': recent_count,
            'baseline_count': baseline_count,
            'multiplier': round(multiplier, 2),
            'is_spike': is_spike,
            'recent_period': f"{lookback_hours}h",
            'timestamp': current_time
        }

        return is_spike, details
    
    def get_ticker_statistics_summary(self, ticker: str, current_time: datetime) -> TickerStats:
        """Get a comprehensive statistical summary for a ticker.
        
        Args:
            ticker (str): Stock ticker symbol
            current_time (datetime): Current time point
            
        Returns:
            TickerStats: Complete statistical summary
        """
        from datetime import timedelta
        
        # Get recent mention data
        start_time = current_time - timedelta(hours=24)
        recent_mentions = database_manager.fetch_ticker_mentions(
            self.connection_pool,
            ticker,
            start_time,
            current_time
        )
        
        # Calculate all statistics
        mention_z = self.calculate_mention_zscore(ticker, current_time)
        sentiment_z = self.calculate_sentiment_zscore(ticker, current_time)
        velocity = self.calculate_mention_velocity(ticker, current_time)
        diversity = self.calculate_subreddit_diversity(ticker, current_time)
        spike, _ = self.detect_mention_spike(ticker, current_time)
        
        # Aggregate mention data
        total_mentions = sum(m.mention_count for m in recent_mentions)
        total_users = sum(m.unique_users for m in recent_mentions)
        total_score = sum(m.total_score for m in recent_mentions)
        total_comments = sum(m.total_comments for m in recent_mentions)
        
        # Calculate weighted avg sentiment
        if recent_mentions and total_mentions > 0:
            weighted_sentiment = sum(
                m.avg_sentiment * m.mention_count for m in recent_mentions
            ) / total_mentions
        else:
            weighted_sentiment = 0.0
        
        return TickerStats(
            ticker=ticker,
            timestamp=current_time,
            mention_count=total_mentions,
            mention_zscore=mention_z,
            mention_velocity=velocity,
            avg_sentiment=round(weighted_sentiment, 4),
            sentiment_zscore=sentiment_z,
            unique_users=total_users,
            total_score=total_score,
            total_comments=total_comments,
            subreddit_diversity=diversity,
            spike_detected=spike
        )

    #=======HELPERS========
    def _aggregate_mentions_by_time(self, mentions: list[MentionDataPoint], hours: int = 1) -> list[tuple[datetime, int]]:
        """Aggregates mention counts into time buckets.

        Args:
            mentions (list[MentionDataPoint]): List of MentionDataPoint objects
            hours (int, optional): Size of time bucket in hours. Defaults to 1.

        Returns:
            list[tuple[datetime, int]]: Timestamp, total_count
        """
        if not mentions:
            return []
        
        buckets = defaultdict(int)

        for m in mentions:
            #Round timestamp to nearest bucket
            bucket_time = m.timestamp.replace(
                minute=0,
                second=0,
                microsecond=0
            )
            #Round further if needed
            if hours > 1:
                hours_diff = bucket_time.hour % hours
                bucket_time = bucket_time.replace(hour=bucket_time.hour - hours_diff)
            
            buckets[bucket_time] += m.mention_count
        
        #sort
        sorted_buckets = sorted(buckets.items(), key=lambda x: x[0])

        return sorted_buckets

    def _aggregate_sentiment_by_time(self, mentions: list[MentionDataPoint], hours: int = 1) -> list[tuple[datetime, float]]:
        """Aggregate weighted sentiment into time buckets.
        
        Args:
            mentions: List of MentionDataPoint objects
            hours: Size of time bucket in hours
            
        Returns:
            List of (timestamp, weighted_avg_sentiment) tuples
        """
        if not mentions:
            return []
        
        buckets = defaultdict(lambda: {'total': 0.0, 'weight': 0})
        
        for m in mentions:
            bucket_time = m.timestamp.replace(minute=0, second=0, microsecond=0)
            if hours > 1:
                hour_diff = bucket_time.hour % hours
                bucket_time = bucket_time.replace(hour=bucket_time.hour - hour_diff)
            
            # Weight sentiment by mention count
            weight = m.mention_count
            buckets[bucket_time]['total'] += m.avg_sentiment * weight
            buckets[bucket_time]['weight'] += weight
        
        # Calculate weighted averages
        result = []
        for timestamp, data in sorted(buckets.items()):
            if data['weight'] > 0:
                avg_sentiment = data['total'] / data['weight']
                result.append((timestamp, avg_sentiment))
        
        return result
    
    def _get_active_tickers(self, start_time: datetime, end_time: datetime, min_mentions: int = 10) -> list[str]:
        """Get list of tickers with activity in the time period.
        
        Args:
            start_time: Start of time range.
            end_time: End of time range.
            min_mentions: Minimum mentions to be considered active.
            
        Returns:
            List of ticker symbols
        """
        conn = self.connection_pool.getconn()
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
            self.connection_pool.putconn(conn)