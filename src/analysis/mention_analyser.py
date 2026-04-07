from collections import defaultdict

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
        return self.sentiment_analyser.analyse_text(post.text)

    def analyse_ticker_sentiment(
        self, posts: list[Post], ticker: str
    ) -> dict[str, float]:
        """Analyses the sentiment of a single ticker across many posts.

        Args:
            posts (list[Post]): The posts in which will be analysed.
            ticker (str): The specific ticker being analysed.

        Returns:
            dict[str, float]: Holds keys 'avg_sentiment', 'positive_ratio', 'negative_ratio'
        """
        sentiments = []

        for post in posts:
            # check that ticker is mentioned
            if ticker.upper() in post.text.upper():
                sentiment = self.analyse_post_sentiment(post)
                sentiments.append(sentiment)

        if not sentiments:
            return {"avg_sentiment": 0.0, "positive_ratio": 0.0, "negative_ratio": 0.0}

        avg_sentiment = sum(sentiments) / len(sentiments)
        positive_ratio = len([s for s in sentiments if s > 0.1]) / len(sentiments)
        negative_ratio = len([s for s in sentiments if s < -0.1]) / len(sentiments)

        return {
            "avg_sentiment": round(avg_sentiment, 4),
            "positive_ratio": round(positive_ratio, 4),
            "negative_ratio": round(negative_ratio, 4),
        }

    def calculate_weighted_sentiment(self, posts: list[Post], ticker: str) -> float:
        """Compute the weighted sentiment for a ticker based on engagement.

        Args:
            posts (list[Post]): Posts to analyse.
            ticker (str): Ticker to analyse.

        Returns:
            float: Weighted average sentiment.
        """
        weighted_sum = 0.0
        total_weight = 0.0

        for post in posts:
            if ticker.upper() in post.text.upper():
                sentiment = self.analyse_post_sentiment(post)

                # Weight based on engagement
                weight = max(1, post.score) + (post.num_comments * 0.5)

                weighted_sum += sentiment * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        return round(weighted_sum / total_weight, 4)

    def get_sentiment_cat_distribution(
        self, posts: list[Post], ticker: str
    ) -> dict[str, int]:
        """Gets the distribution of sentiment categories for a ticker.

        Args:
            posts (list[Post]): Posts to analyse.
            ticker (str): Ticker to analyse.

        Returns:
            dict[str, int]: Dict mapping sentiment category to count
        """
        distribution = defaultdict(int)

        for post in posts:
            if ticker.upper() in post.text.upper():
                sentiment = self.analyse_post_sentiment(post)
                category = self.sentiment_analyser.categorise_sentiment(sentiment)
                distribution[category.name] += 1

        return dict(distribution)

    def analyse_sentiment_trend(
        self, posts: list[Post], ticker: str
    ) -> list[tuple[float, float]]:
        """Analyse how sentiment changes overtime for a ticker.

        Args:
            posts (list[Post]): Posts to analyse (should be time-ordered).
            ticker (str): ticker to analyse.

        Returns:
            list[tuple[float, float]]: (timestamp, sentiment_score)
        """
        sentiment_timeline = []

        for post in posts:
            if ticker.upper() in post.text.upper():
                sentiment = self.analyse_post_sentiment(post)
                sentiment_timeline.append((post.created_utc, sentiment))

        # order by timestamp
        sentiment_timeline.sort(key=lambda x: x[0])

        return sentiment_timeline

    def compare_subreddit_sentiment(
        self, posts: list[Post], ticker: str
    ) -> dict[str, float]:
        """Compare sentiment across subreddits for a ticker.

        Args:
            posts (list[Post]): Posts to analyse.
            ticker (str): ticker to analyse.

        Returns:
            dict[str, float]: Maps subreddit name to average sentiment
        """
        subreddit_sentiments = defaultdict(list)

        for post in posts:
            if ticker.upper() in post.text.upper():
                sentiment = self.analyse_post_sentiment(post)
                subreddit_sentiments[post.subreddit].append(sentiment)

        # Calculate averages
        result = {}
        for subreddit, sentiments in subreddit_sentiments.items():
            result[subreddit] = round(sum(sentiments) / len(sentiments), 4)

        return result
