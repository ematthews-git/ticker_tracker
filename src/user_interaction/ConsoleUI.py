from matplotlib import pyplot as plt
import numpy as np
from datetime import datetime, timedelta

import sys
from pathlib import Path

# Add parent directory to path to import config and models
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH
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


def graph_ticker(ticker: str):
    #get times
    try:
        start_time_input = int(input("Enter the number of days you want to view(Max 3): "))
        if start_time_input > 3: start_time_input = 3
        now = datetime.now()
        dif = timedelta(days=start_time_input)
        start_time = now - dif

        plot_points = list(Database.fetch_ticker_mentions(DB_PATH, ticker, start_time, now))

        x_axis = []
        y_axis = []
        for point in plot_points:
            x_axis.append(point.timestamp)
            y_axis.append(point.mention_count)
    
        plt.plot(x_axis, y_axis)
        plt.show()

    except Exception as e:
        print(f"[ERROR] error with graphing ticker: {e}")

if __name__ == "__main__":
    main()


    