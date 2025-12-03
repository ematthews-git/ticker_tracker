from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

from config import DB_URL, SUBREDDITS
from models import MentionDataPoint, TickerStats
from storage import database_manager
from utils import helper
from psycopg2.pool import SimpleConnectionPool

class Visualiser:
    """The visualiser communicates with the database to visualise basic information"""
    def __init__(self, connection_pool=None) -> None:
        if connection_pool is None:
            # Create a pool if one isn't provided
            self.connection_pool = SimpleConnectionPool(
                minconn=1,
                maxconn=5,
                dsn=DB_URL
            )
        else:
            self.connection_pool = connection_pool

    def graph_ticker(self, ticker: str):
        try:
            #get times
            try:
                start_time_input = input("Enter timeframe(e.g '12h', '1d', '1w'): ")
                now = datetime.now(timezone.utc)
                dif = helper.parse_time_input(start_time_input)
                start_time = now - dif
            except ValueError as e:
                print(f"Timeframe formatted incorrectly: {e}")
                return

            plot_points = list(database_manager.fetch_ticker_mentions(self.connection_pool, ticker, start_time, now))

            #Convert to dataframe
            df = pd.DataFrame([
                {
                    'timestamp': point.timestamp,
                    'mention_count': point.mention_count,
                    'subreddit': point.subreddit
                }
                for point in plot_points
            ])
            #add points
            for sub in SUBREDDITS:
                sub_data = df[df['subreddit'] == sub]
                plt.plot(sub_data['timestamp'], sub_data['mention_count'], label=sub)

            #Add cumulative line
            # cumulative = df.groupby('timestamp')['mention_count'].sum().reset_index()
            # plt.plot(cumulative['timestamp'], cumulative['mention_count'], 
            #          label = 'Total', linestyle='--')

            #plot
            plt.title(f"""{ticker.upper()} mentions from 
                    {start_time.replace(microsecond=0, second=0, minute=0)} to {now.replace(microsecond=0, second=0, minute=0)}""")
            plt.legend()
            plt.grid(True)
            plt.tight_layout()
            plt.show()
        except Exception as e:
            print(f"[ERROR] error with graphing ticker: {e}")

    def display_popular_tickers(self):
        """Asks the user for parameters and displays the most popular tickers based on those parameters."""
        try: 
            timeframe = input("Enter timeframe(e.g '12h', '1d', '1w'): ")
            now = datetime.now(timezone.utc)
            dif = helper.parse_time_input(timeframe)
        except Exception as e:
            print(f"Timeframe formatted incorrectly: {e}")
            return

        start_time = now - dif

        amount = int(input("How many tickers would you like to see(min = 10, max = 30): "))
        if amount > 30: amount = 30
        elif amount < 10: amount = 10

        popular_tickers = database_manager.fetch_popular_tickers(self.connection_pool, start_time, now, amount)

        #displaying
        for ticker, points in popular_tickers.items():
            total_mentions = sum(dp.mention_count for dp in points)
            print(f"{ticker}: {total_mentions}")
    
    def display_growth_tickers(self):
        """Asks the user for parameters and displays the tickers with the highest growth based on those paramters"""
        try:
            timeframe = input("Enter timeframe(e.g '12h', '1d', '1w')")
            now = datetime.now()
            dif = helper.parse_time_input(timeframe)
        except Exception as e:
            print(f"Timeframe formatted incorrectly: {e}")
            return
        
        start_time = now - dif

        amount = int(input("How many tickers would you like to see (min = 10, max = 30)"))
        if amount > 30: amount = 30
        elif amount < 10: amount = 10

        growth_tickers = database_manager.fetch_growth_tickers(self.connection_pool, start_time, now, amount)

        if not growth_tickers:
            print("\nNo growth tickers found in this timeframe")
            return

        #display
        for ticker, (growth_rate, mention_points) in growth_tickers.items():
            total_mentions = sum(dp.mention_count for dp in mention_points)
            #This ensures the tickers displayed are actually relevant
            if total_mentions < 4:
                continue
            print(f"{ticker}: {growth_rate:.2f}% growth ({total_mentions} total mentions)")
    
    def display_hot_tickers(self):
        """Displays anomalous tickers (Highest Z-Score)"""
        try:
            timeframe = input("Enter timeframe(e.g '12h', '1d', '1w')")
            now = datetime.now()
            dif = helper.parse_time_input(timeframe)
        except Exception as e:
            print(f"Timeframe formatted incorrectly: {e}")
            return
        
        start_time = now - dif

        amount = int(input("How many tickers would you like to see (min = 5, max = 30): "))
        if amount > 30: amount = 30
        elif amount < 5: amount = 5
        
        # Fetch hot tickers from ticker_statistics table
        hot_tickers = self._fetch_hot_tickers(start_time, now, amount)
        
        if not hot_tickers:
            print("\nNo hot tickers found in this timeframe")
            print("(Make sure the statistics collector has been running)")
            return
        
        # Display results
        print(f"\nTop {len(hot_tickers)} Hot Tickers (Highest Z-Scores):")
        print("=" * 120)
        print(f"{'Rank':<6} {'Ticker':<8} {'MentionZ':<10} {'SentZ':<10} {'Velocity':<12} {'Diversity':<10} {'Mentions':<10} {'Sentiment':<10} {'Timestamp':<20}")
        print("=" * 120)
        
        for i, stats in enumerate(hot_tickers, 1):
            mention_z_str = f"{stats.mention_zscore:.2f}" if stats.mention_zscore else "N/A"
            sent_z_str = f"{stats.sentiment_zscore:.2f}" if stats.sentiment_zscore else "N/A"
            
            print(f"{i:<6} {stats.ticker:<8} {mention_z_str:<10} {sent_z_str:<10} "
                  f"{stats.mention_velocity:<12.2f} {stats.subreddit_diversity:<10} "
                  f"{stats.mention_count:<10} {stats.avg_sentiment:<10.3f} "
                  f"{stats.timestamp.strftime('%Y-%m-%d %H:%M'):<20}")
        
        # Show detailed view of top ticker
        if hot_tickers:
            print("\n" + "=" * 120)
            print(f"DETAILED VIEW: #{1} {hot_tickers[0].ticker}")
            print("=" * 120)
            
            top = hot_tickers[0]
            
            print(f"\nStatistics at {top.timestamp.strftime('%Y-%m-%d %H:%M UTC')}:")
            print(f"  Mention Z-Score: {top.mention_zscore:.2f}" if top.mention_zscore else "  Mention Z-Score: N/A")
            print(f"  Sentiment Z-Score: {top.sentiment_zscore:.2f}" if top.sentiment_zscore else "  Sentiment Z-Score: N/A")
            print(f"  Mention Velocity: {top.mention_velocity:.2f} mentions/hour")
            print(f"  Subreddit Diversity: {top.subreddit_diversity} subreddits")
            print(f"  Total Mentions: {top.mention_count}")
            print(f"  Average Sentiment: {top.avg_sentiment:.3f} (-1 to +1)")
            print(f"  Spike Detected: {'Yes' if top.spike_detected else 'No'}")
            
            # Show anomaly reasons
            reasons = top.get_anomaly_reasons()
            if reasons:
                print(f"\nWhy it's anomalous:")
                for reason in reasons:
                    print(f"  • {reason}")
        
    
    def _fetch_hot_tickers(self, start_time: datetime, end_time: datetime, limit: int) -> list[TickerStats]:
        """Fetch tickers with highest Z-scores from ticker_statistics table.
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of tickers to return
            
        Returns:
            List of TickerStats objects ordered by mention Z-score
        """
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        
        try:
            # Get the most recent statistics for each ticker in the timeframe
            # and order by mention_zscore
            cursor.execute("""
                WITH ranked_stats AS (
                    SELECT 
                        ticker, timestamp, mention_count, mention_zscore, mention_velocity,
                        avg_sentiment, sentiment_zscore, unique_users, total_score,
                        total_comments, subreddit_diversity, spike_detected,
                        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp DESC) as rn
                    FROM ticker_statistics
                    WHERE timestamp BETWEEN %s AND %s
                    AND mention_zscore IS NOT NULL
                )
                SELECT 
                    ticker, timestamp, mention_count, mention_zscore, mention_velocity,
                    avg_sentiment, sentiment_zscore, unique_users, total_score,
                    total_comments, subreddit_diversity, spike_detected
                FROM ranked_stats
                WHERE rn = 1
                ORDER BY mention_zscore DESC NULLS LAST
                LIMIT %s
            """, (start_time, end_time, limit))
            
            rows = cursor.fetchall()
            return [TickerStats.from_db_row(row) for row in rows]
            
        except Exception as e:
            print(f"Error fetching hot tickers: {e}")
            return []
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
        
