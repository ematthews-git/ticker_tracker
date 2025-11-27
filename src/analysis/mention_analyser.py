import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Post, MentionDataPoint
from analysis.sentiment_analyser import SentimentAnalyser
import logging

logger = logging.getLogger(__name__)

class MentionAnalyser:
    """Handles analysis relating to mentions and the MentionDataPoint dataclass"""

    def __init__(self):
        self.sentiment_analyser = SentimentAnalyser()
    
    def analyse_post_sentiment(self, post: Post) -> float:
        """Analyse the sentiment of a post.

        Args:
            post (Post): The post to analyse.

        Returns:
            float: Sentiment score between -1 and 1
        """
        
