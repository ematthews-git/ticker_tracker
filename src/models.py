from dataclasses import dataclass
from typing import Literal, Optional
from datetime import datetime, timezone

@dataclass(frozen=True)
class Post:
    """Represents a reddit post or comment

    Attributes:
        #identifiers
        id (str): The unique Reddit post or comment ID (e.g., 'abc123').
        subreddit (str): The subreddit in which the post/comment originated
        type (Literal["post", "comment"]): Indicates whether the entry is a post or comment.
        text (str): The combined title and body (or comment text).
        created_utc (float): The UTC timestamp of creation (as returned by PRAW).
        origin_id (Optional[str]): A comments origin post id. None for posts.
        user_id (str): The username of the post/comments author.

        #Engagement metrics
        score (int): The upvote score (upvotes - downvotes).
        num_comments (int): Number of comments (0 for comments).

        #Author Quality
        author_quality (Optional[float]): The calculated author quality score


    """
    id: str
    subreddit: str
    type: Literal["post", "comment"]
    text: str
    created_utc: float
    origin_id: Optional[str]
    user_id: str
    #engagement
    score: int
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
    """Represents a single ticker mention data point
    
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

