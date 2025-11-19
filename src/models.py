from dataclasses import dataclass
from typing import Literal, Optional
from datetime import datetime

@dataclass(frozen=True)
class Post:
    """Represents a reddit post or comment

    Attributes:
        id (str): The unique Reddit post or comment ID (e.g., 'abc123').
        subreddit (str): The subreddit in which the post/comment originated
        type (Literal["post", "comment"]): Indicates whether the entry is a post or comment.
        text (str): The combined title and body (or comment text).
        created_utc (float): The UTC timestamp of creation (as returned by PRAW).
        origin_id (Optional[str]): A comments origin post id. None for posts.
    """
    id: str
    subreddit: str
    type: Literal["post", "comment"]
    text: str
    created_utc: float
    origin_id: Optional[str]

@dataclass(frozen=True)
class MentionDataPoint:
    """Represents a single ticker mention data point
    
    Attributes:
        ticker (str): The stock ticker symbol (e.g., 'AAPL').
        subreddit (str): The subreddit where the mention occurred.
        timestamp (datetime): The timestamp when the mention was recorded.
        mention_count (int): The number of times the ticker was mentioned.
    """
    ticker: str
    subreddit: str
    timestamp: datetime
    mention_count: int

