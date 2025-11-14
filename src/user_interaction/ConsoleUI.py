from matplotlib import pyplot as plt
import numpy as np
from datetime import datetime, timedelta

import sys
from pathlib import Path

# Add parent directory to path to import config and models
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH, SUBREDDITS
from models import MentionDataPoint
from storage import Database

def main():
    print("=" * 50)
    print("Reddit Ticker Mention Collector \n data viewer")
    print("=" * 50)

    entry = " "
    while entry != "9":
        print("1: Enter ticker to graph it")
        print("2: List tickers by highest Z score")
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


def graph_ticker(ticker: str):
    try:
        #get times
        start_time_input = int(input("Enter the number of days you want to view(Max 3): "))
        if start_time_input > 3: start_time_input = 3
        now = datetime.now()
        dif = timedelta(days=start_time_input)
        start_time = now - dif

        ####
        plot_points = list(Database.fetch_ticker_mentions(DB_PATH, ticker, start_time, now))

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

if __name__ == "__main__":
    main()

