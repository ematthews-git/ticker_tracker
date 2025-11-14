from matplotlib import pyplot as plt

import sys
from pathlib import Path

# Add parent directory to path to import config and models
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_PATH

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

        if entry == 1:
            print("*" * 50)
            print("1: Enter ticker to graph it")
            print("*" * 50)
            
            ticker = input("Enter desired ticker(e.g)'ABC': ")
            graph_ticker(ticker)


def graph_ticker(ticker: str):
    print("67")

    