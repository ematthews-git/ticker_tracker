from matplotlib import pyplot as plt
import pandas as pd
from datetime import datetime, timezone

from config import DB_URL, SUBREDDITS
from storage import database_manager
from utils import helper
from psycopg2.pool import SimpleConnectionPool


class Visualiser:
    """The visualiser communicates with the database to visualise basic information"""

    def __init__(self, connection_pool=None) -> None:
        if connection_pool is None:
            # Create a pool if one isn't provided
            self.connection_pool = SimpleConnectionPool(
                minconn=1, maxconn=5, dsn=DB_URL
            )
        else:
            self.connection_pool = connection_pool

    def graph_ticker(self, ticker: str):
        try:
            # get times
            try:
                start_time_input = input("Enter timeframe(e.g '12h', '1d', '1w'): ")
                now = datetime.now(timezone.utc)
                dif = helper.parse_time_input(start_time_input)
                start_time = now - dif
            except ValueError as e:
                print(f"Timeframe formatted incorrectly: {e}")
                return

            plot_points = list(
                database_manager.fetch_ticker_mentions(
                    self.connection_pool, ticker, start_time, now
                )
            )

            # Convert to dataframe
            df = pd.DataFrame(
                [
                    {
                        "timestamp": point.timestamp,
                        "mention_count": point.mention_count,
                        "subreddit": point.subreddit,
                    }
                    for point in plot_points
                ]
            )
            # add points
            for sub in SUBREDDITS:
                sub_data = df[df["subreddit"] == sub]
                plt.plot(sub_data["timestamp"], sub_data["mention_count"], label=sub)

            # Add cumulative line
            cumulative = df.groupby("timestamp")["mention_count"].sum().reset_index()
            plt.plot(
                cumulative["timestamp"],
                cumulative["mention_count"],
                label="Total",
                linestyle="--",
            )

            # plot
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

        amount = int(
            input("How many tickers would you like to see(min = 10, max = 30): ")
        )
        if amount > 30:
            amount = 30
        elif amount < 10:
            amount = 10

        popular_tickers = database_manager.fetch_popular_tickers(
            self.connection_pool, start_time, now, amount
        )

        # displaying
        for ticker, points in popular_tickers.items():
            total_mentions = sum(dp.mention_count for dp in points)
            print(f"{ticker}: {total_mentions}")
