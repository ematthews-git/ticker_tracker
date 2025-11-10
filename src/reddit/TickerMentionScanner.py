import re

class TickerMentionScanner:
    def __init__(self, valid_tickers):
        self.valid = set(valid_tickers)
    
    def count_mentions(self, text_list):
        counts = {}
        for text in text_list:
            words = re.findall(r'\b[A-Z]{2,5}\b', text) #capital letters + 2 to 5 characters
            for w in words:
                if w in self.valid:
                    counts[w] = counts.get(w, 0) + 1 #existing val += 1
        return counts