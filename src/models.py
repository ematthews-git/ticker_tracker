from dataclasses import dataclass
from typing import Literal, Optional
from datetime import datetime, timezone
from enum import Enum, auto

@dataclass(frozen=True)
class Post:
    """Represents a reddit post or comment

    Attributes:
        #identifiers
        id (str): The unique Reddit post or comment ID (e.g., 'abc123').
        subreddit (str): The subreddit in which the post/comment originated
        type (Literal["post", "comment"]): Indicates whether the entry is a post or comment.
        text (str): The combined title and body (or comment text).
        link_flair_text (Optional[str]): The flair attached to the post.
        created_utc (float): The UTC timestamp of creation (as returned by PRAW).
        origin_id (Optional[str]): A comments origin post id. None for posts.
        user_id (str): The username of the post/comments author.

        #Engagement metrics
        score (int): The upvote score (upvotes - downvotes).
        upvote_ratio (Optional[float]): The ratio of upvotes to downvotes(None for comments).
        num_comments (int): Number of comments (0 for comments).

        #Author Quality
        author_quality (Optional[float]): The calculated author quality score
    """
    id: str
    subreddit: str
    type: Literal["post", "comment"]
    text: str
    link_flair_text: Optional[str]
    created_utc: float
    origin_id: Optional[str]
    user_id: str
    #engagement
    score: int
    upvote_ratio: Optional[float]
    num_comments: int
    #author quality snapshot score
    author_quality: Optional[float]

@dataclass(frozen=False)
class Author:
    """Represents an author of a reddit post or comment.

    Attributes:
        username (str): The authors username.
        created_utc (Optional[datetime]): The UTC timestamp of the authors account creation.
        comment_karma (int): The authors karma on comments.
        link_karma (int): The authors karma on posts.
        last_updated (datetime): When the users information was last updated in the database
    """
    username: str
    created_utc: Optional[datetime]
    comment_karma: int
    link_karma: int
    last_updated: datetime

    @classmethod
    def deleted(cls) -> 'Author':
        """Create an Author instance representing a deleted user"""
        return cls(
            username="[DELETED]",
            created_utc= None,
            comment_karma = 0,
            link_karma = 0,
            last_updated = datetime.now(timezone.utc)
        )


@dataclass(frozen=True)
class MentionDataPoint:
    """Represents a single ticker mention data point.
    
    Attributes:
        ticker (str): The stock ticker symbol (e.g., 'AAPL').
        subreddit (str): The subreddit where the mention occurred.
        timestamp (datetime): The timestamp when the mention was recorded.
        mention_count (int): The number of times the ticker was mentioned.
        unique_users (int): Number of unique users mentioning the ticker.
        total_score (int): Sum of scores from all posts mentioning the ticker.
        total_comments (int): Sum of comments from all posts mentioning the ticker.
        avg_sentiment (float): Average sentiment score (-1 to 1)
    """
    ticker: str
    subreddit: str
    timestamp: datetime
    mention_count: int
    unique_users: int
    total_score: int
    total_comments: int
    avg_sentiment: float

@dataclass
class TickerStats:
    """Represents a collection of statistics relating to a ticker at a point in time.

    Attributes:
        ticker (str): Stock ticker symbol (e.g., 'AAPL').
        timestamp (datetime): Time point these statistics represent.
        
        # Mention metrics
        mention_count (int): Total mentions in the period.
        mention_zscore (Optional[float]): Z-score for mentions (-∞ to +∞, typically -3 to +3).
        mention_velocity (float): Rate of change in mentions per hour.
        
        # Sentiment metrics
        avg_sentiment (float): Average sentiment score (-1 to 1).
        sentiment_zscore (Optional[float]): Z-score for sentiment.
        
        # Engagement metrics
        unique_users (int): Number of unique users mentioning ticker.
        total_score (int): Sum of post scores (upvotes - downvotes).
        total_comments (int): Sum of comment counts.
        subreddit_diversity (int): Number of unique subreddits.
        
        # Anomaly flags
        spike_detected (bool): Whether a sudden spike was detected.
    """
    ticker: str
    timestamp: datetime
    
    # Mention metrics
    mention_count: int
    mention_zscore: Optional[float]
    mention_velocity: float
    
    # Sentiment metrics
    avg_sentiment: float
    sentiment_zscore: Optional[float]
    
    # Engagement metrics
    unique_users: int
    total_score: int
    total_comments: int
    subreddit_diversity: int
    
    # Anomaly flags
    spike_detected: bool

    def is_anomalous(self, mention_threshold: float = 2.0, sentiment_threshold: float = 1.5, velocity_threshold: float = 5.0) -> bool:
        """Check if this ticker shows anomalous activity.
        
        Args:
            mention_threshold: Minimum Z-score for mentions.
            sentiment_threshold: Minimum Z-score for sentiment (absolute value).
            velocity_threshold: Minimum velocity (mentions/hour).
            
        Returns:
            bool: True if ticker meets any anomaly threshold.
        """
        return (
            (self.mention_zscore is not None and self.mention_zscore >= mention_threshold) or
            (self.sentiment_zscore is not None and abs(self.sentiment_zscore) >= sentiment_threshold) or
            (self.mention_velocity >= velocity_threshold) or
            self.spike_detected
        )
    
    def get_anomaly_reasons(self) -> list[str]:
        """Get human-readable reasons why this ticker is anomalous.
        
        Returns:
            list[str]: List of reasons (e.g., "High mention Z-score: 3.2").
        """
        reasons = []
        
        if self.mention_zscore and self.mention_zscore >= 2.0:
            reasons.append(f"High mention Z-score: {self.mention_zscore:.2f}")
        
        if self.sentiment_zscore and abs(self.sentiment_zscore) >= 1.5:
            direction = "positive" if self.sentiment_zscore > 0 else "negative"
            reasons.append(f"Unusual {direction} sentiment: {abs(self.sentiment_zscore):.2f}")
        
        if self.mention_velocity >= 5.0:
            reasons.append(f"Accelerating mentions: {self.mention_velocity:.2f}/hour")
        
        if self.spike_detected:
            reasons.append("Sudden spike detected")
        
        if self.subreddit_diversity >= 4:
            reasons.append(f"Broad interest: {self.subreddit_diversity} subreddits")
        
        return reasons
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization or database storage.
        
        Returns:
            dict: Dictionary representation.
        """
        return {
            'ticker': self.ticker,
            'timestamp': self.timestamp.isoformat(),
            'mention_count': self.mention_count,
            'mention_zscore': self.mention_zscore,
            'mention_velocity': self.mention_velocity,
            'avg_sentiment': self.avg_sentiment,
            'sentiment_zscore': self.sentiment_zscore,
            'unique_users': self.unique_users,
            'total_score': self.total_score,
            'total_comments': self.total_comments,
            'subreddit_diversity': self.subreddit_diversity,
            'spike_detected': self.spike_detected
        }
    
    @classmethod
    def from_db_row(cls, row: tuple) -> 'TickerStats':
        """Create TickerStats from database query result.
        
        Args:
            row: Tuple from database query (ticker, timestamp, mention_count, ...).
            
        Returns:
            TickerStats: Instance created from row data.
        """
        return cls(
            ticker=row[0],
            timestamp=row[1],
            mention_count=row[2],
            mention_zscore=row[3],
            mention_velocity=row[4],
            avg_sentiment=row[5],
            sentiment_zscore=row[6],
            unique_users=row[7],
            total_score=row[8],
            total_comments=row[9],
            subreddit_diversity=row[10],
            spike_detected=row[11]
        )

class SentimentCategory(Enum):
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"