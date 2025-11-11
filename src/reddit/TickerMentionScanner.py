import re

class TickerMentionScanner:
    """Scans for Ticker Mentions

    """
    def __init__(self, invalid_tickers):
        self.invalid = set(invalid_tickers)
    
    #Counts mentions of valid tickers into dictionary from a list of text
    def count_mentions(self, text_list):
        """finds the mention of any valid ticker in the list of text parsed

        Args:
            text_list (Iterable[str]): The list of text items to search

        Returns:
            dict[str, int]: A dictionary mapping each ticker symbol to the number of times it was mentioned
        """
        counts = {}
        for text in text_list:
            words = re.findall(r'\b[A-Z]{2,5}\b', text) #capital letters + 2 to 5 characters
            for w in words:
                if w not in self.invalid:
                    counts[w] = counts.get(w, 0) + 1 #existing val += 1
        return counts