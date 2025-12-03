from visualiser import Visualiser

def main():
    print("=" * 50)
    print("Reddit Ticker Mention Collector \n data viewer")
    print("=" * 50)

    visualiser = Visualiser()

    entry = " "
    while entry != "9":
        print("1: Enter ticker to graph it")
        print("2: List most popular tickers")
        print("3: Find new tickers")
        print("4: Show highest z-scores")
        print("9: Exit")

        entry = input("Enter number: ")

        if entry == "1":
            print("*" * 50)
            print("1: Enter ticker to graph it")
            print("*" * 50)
            
            ticker = input("Enter desired ticker(e.g 'ABC'): ")
            visualiser.graph_ticker(ticker)
            print("Graphing complete")
        elif entry == "2":
            print("*" * 50)
            print("2: List most popular tickers")
            print("*" * 50)
            visualiser.display_popular_tickers()
        elif entry == "3":
            print("*" * 50)
            print("3: Emerging tickers")
            print("*" * 50)
            visualiser.display_growth_tickers()
        elif entry == "4":
            print("*" * 50)
            print("4: Hottest tickers")
            print("*" * 50)
            visualiser.display_hot_tickers()



def display_emerging_tickers():
    pass

if __name__ == "__main__":
    main()

