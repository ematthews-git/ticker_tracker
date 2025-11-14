from dataclasses import dataclass
from typing import Literal
import datetime

@dataclass
class Post:
    """Represents a reddit post or comment

    Attributes:
        id (str): The unique Reddit post or comment ID (e.g., 'abc123').
        subreddit (str): The subreddit in which the post/comment originated
        type (Literal["post", "comment"]): Indicates whether the entry is a post or comment.
        text (str): The combined title and body (or comment text).
        created_utc (float): The UTC timestamp of creation (as returned by PRAW).
    """
    id: str
    subreddit: str
    type: Literal["post", "comment"]
    text: str
    created_utc: float

@dataclass
class MentionDataPoint:
    ticker: str
    subreddit: str
    timestamp: datetime
    mention_count: int

