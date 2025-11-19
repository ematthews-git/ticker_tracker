from matplotlib import pyplot as plt
import numpy as np
from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path

# Add parent directory to path to import config and models
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_URL, SUBREDDITS
from models import MentionDataPoint
from storage import Database

def main():
    print("=" * 50)
    print("Reddit Ticker Mention Collector \n data viewer")
    print("=" * 50)

    entry = " "
    while entry != "9":
        print("1: Enter ticker to graph it")
        print("2: List most popular tickers")
        print("3: Find new tickers")
        print("9: Exit")

        entry = input("Enter number: ")

        if entry == "1":
            print("*" * 50)
            print("1: Enter ticker to graph it")
            print("*" * 50)
            
            ticker = input("Enter desired ticker(e.g 'ABC'): ")
            graph_ticker(ticker)
            print("Graphing complete")
            entry = ' '
            continue
        elif entry == "2":
            print("*" * 50)
            print("2: List most popular tickers")
            print("*" * 50)
            display_popular_tickers()
            entry = ''
            continue

            

def graph_ticker(ticker: str):
    try:
        #get times
        start_time_input = int(input("Enter the number of days you want to view(Max 3): "))
        if start_time_input > 3: start_time_input = 3
        now = datetime.now(timezone.utc)
        dif = timedelta(days=start_time_input)
        start_time = now - dif

        ####
        plot_points = list(Database.fetch_ticker_mentions(DB_URL, ticker, start_time, now))

        #these are lists containg each axis list for the subreddits
        all_x_axis = []
        all_y_axis = []

        for sub in SUBREDDITS:
            x = []
            y = []
            for point in plot_points:
                if point.subreddit == sub:
                    x.append(point.timestamp)
                    y.append(point.mention_count)
            
            all_x_axis.append(x)
            all_y_axis.append(y)
        
        for i, sub in enumerate(SUBREDDITS):
            plt.plot(all_x_axis[i], all_y_axis[i], label=sub)

        plt.title(f"""{ticker.upper()} mentions from 
                  {start_time.replace(microsecond=0, second=0, minute=0)} to {now.replace(microsecond=0, second=0, minute=0)}""")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.show()

    except Exception as e:
        print(f"[ERROR] error with graphing ticker: {e}")

def display_popular_tickers():
    """Asks the user for parameters and displays the most popular tickers based on those parameters.
    """
    try: 
        timeframe = input("Enter timeframe(e.g '12h', '1d', '1w'): ")
        now = datetime.now(timezone.utc)
        if timeframe[-1] == "h":
            dif = timedelta(hours=int(timeframe[:-1]))
        elif timeframe[-1] == "d":
            dif = timedelta(days=int(timeframe[:-1]))
        elif timeframe[-1] == "w":
            dif = timedelta(weeks=int(timeframe[:-1]))
        else:
            print("Timeframe formatted incorrectly")
            return
    except:
        print("Timeframe formatted incorrectly")

    start_time = now - dif

    amount = int(input("How many tickers would you like to see(min = 10, max = 30): "))
    if amount > 30: amount = 30
    elif amount < 10: amount = 10

    popular_tickers = Database.fetch_popular_tickers(DB_URL, start_time, now, amount)
    print(len(popular_tickers))

    #displaying
    for ticker, points in popular_tickers.items():
        total_mentions = sum(dp.mention_count for dp in points)
        print(f"{ticker}: {total_mentions}")


if __name__ == "__main__":
    main()

