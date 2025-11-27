from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import re
import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from models import SentimentCategory

logger = logging.getLogger(__name__)

class SentimentAnalyser:
    """Analyses sentiment of Reddit posts/comments"""

    def __init__(self):
        self.analyser = SentimentIntensityAnalyzer()

        #{word: score}, -4 to 4
        lexicon = {
            # Bullish terms
            'moon': 3.5,
            'mooning': 3.5,
            'rocket': 3.0,
            'rockets': 3.0,
            'bullish': 3.0,
            'breakout': 2.5,
            'squeeze': 2.5,
            'gamma': 2.0,
            'calls': 1.5,
            'buy': 2.0,
            'long': 1.5,
            'undervalued': 2.5,
            'gains': 2.5,
            'tendies': 3.0,
            'diamond': 2.0,
            'hold': 1.5,
            'hodl': 2.0,
            'accumulate': 2.0,
            'catalyst': 2.0,
            'rally': 2.5,
            'bounce': 1.5,
            'support': 1.0,
            
            # Bearish terms
            'bearish': -3.0,
            'crash': -3.5,
            'dump': -3.0,
            'dumping': -3.0,
            'rug': -4.0,
            'rugpull': -4.0,
            'overvalued': -2.5,
            'puts': -1.5,
            'sell': -2.0,
            'bag': -2.5,
            'bags': -2.5,
            'bagholder': -2.0,
            'bagholding': -2.0,
            'loss': -2.5,
            'losses': -2.5,
            'red': -1.5,
            'resistance': -1.0,
            'dilution': -2.5,
            'scam': -4.0,
            'fomo': -1.5,
            
            # Neutral/context terms
            'dd': 0.5,  # Due diligence - slightly positive
            'dip': 0.0,  # Can be positive (buying opportunity) or negative
            'yolo': 0.0,  # Neutral, just risky
            'short': 0.0  #Reddit rarely supports short - probably indicates squeeze
        }

        #Update VADER with lexicon
        self.analyser.lexicon.update(lexicon)

        self.bull_patterns = {
            r'to\s+the\s+moon',
            r'🚀+',
            r'💎+\s*🙌+',
            r'lets?\s+go+',
            r'lfg',   
        }

        self.bear_patterns = [
            r'rug\s*pull',
            r'stay\s+away',
            r'avoid',
            r'don\'?t\s+buy',
        ]

    def _apply_pattern_boost(self, text: str, base_score: float) -> float:
        """Apply sentiment boosts based on pattern matching.

        Args:
            text (str): The text to analyse.
            base_score (float): The base original score.

        Returns:
            float: Updated sentiment score
        """
        text_lower = text.lower()
        boost = 0.0

        #check bulls
        for pattern in self.bull_patterns:
            if re.search(pattern, text_lower):
                boost += 0.2
        
        #check bears
        for pattern in self.bear_patterns:
            if re.search(pattern, text_lower):
                boost -= 0.2
        
        updated = base_score + boost
        #clamps between -1 and 1
        return max(-1.0, min(1.0, updated))
    
    def _normalise_text(self, text: str) -> str:
        """Clean text for analyis.

        Args:
            text (str): Raw text from post/comment

        Returns:
            str: Cleaned text
        """
        #Remove markdown formatting
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        #remove any urls
        text = re.sub(r"(https?://\S+|www\.\S+|\b\w+\.\w{2,}\S*)", "", text)
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def analyse_text(self, text: str) -> float:
        """Analyses sentiment of a text.

        Args:
            text (str): Text to analyse

        Returns:
            float: Sentiment score betweeen -1 and 1
        """
        if not text or not text.strip():
            return 0.0
        
        #Clean text
        cleaned_text = self._normalise_text(text)

        #Get score from VADER
        scores = self.analyser.polarity_scores(cleaned_text)

        #Use compound score (between -1 and 1)
        score = scores['compound']

        #Apply pattern adjustments
        final_score = self._apply_pattern_boost(cleaned_text, score)

        return round(final_score, 4)
    
    def analyse_batch(self, texts: list[str]) -> list[float]:
        """Analyses sentiment of a list of texts.

        Args:
            texts (list[str]): List of texts to analyse

        Returns:
            list[float]: List of sentiment scores
        """
        return [self.analyse_text(text) for text in texts]
    
    def categorise_sentiment(self, score: float) -> SentimentCategory:
        """Categorise a sentiment score into a label.

        Args:
            score (float): Sentiment score between -1 and 1.

        Returns:
            SentimentCategory: The appropriate category.
        """
        if score >= 0.5:
            return SentimentCategory.VERY_POSITIVE
        elif score >= 0.1:
            return SentimentCategory.POSITIVE
        elif score >= -0.1:
            return SentimentCategory.NEUTRAL
        elif score >= -0.5:
            return SentimentCategory.NEGATIVE
        else:
            return SentimentCategory.VERY_NEGATIVE
