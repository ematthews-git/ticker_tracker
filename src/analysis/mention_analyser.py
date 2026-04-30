from collections import defaultdict

from models import Post
from analysis.sentiment_analyser import SentimentAnalyser
import logging

logger = logging.getLogger(__name__)


_MIN_POST_LENGTH = 15
_DOWNVOTE_DAMPEN_FACTOR = 0.25


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

    def _effective_sentiment(self, post: Post) -> float:
        """Return the post's sentiment adjusted for community rejection.

        Posts with negative upvote scores contribute at a quarter weight.
        """
        sentiment = self.analyse_post_sentiment(post)
        if post.score < 0:
            sentiment *= _DOWNVOTE_DAMPEN_FACTOR
        return sentiment

    def qualifying_sentiments(self, posts: list[Post], ticker: str) -> list[float]:
        """Return effective sentiments for posts that mention `ticker` and pass the
        length filter. Exposed so the scanner can derive sentiment_sum / post_count
        without re-running this loop.
        """
        sentiments = []
        for post in posts:
            if ticker.upper() not in post.text.upper():
                continue
            # Skip ticker-only / near-empty posts — they produce 0.0 scores
            # that drag the mean toward neutral without carrying signal.
            if len(post.text.strip()) < _MIN_POST_LENGTH:
                continue
            sentiments.append(self._effective_sentiment(post))
        return sentiments

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
        sentiments = self.qualifying_sentiments(posts, ticker)

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
