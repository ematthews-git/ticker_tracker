from dataclasses import dataclass
from typing import Literal, Optional
from datetime import datetime

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
        author_created_utc (float): Account creation timestamp
        author_comment_karma (int): The authors comment karma
        author_link_karma (int): The authors link(post) karma


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
    #author quality
    author_created_utc: float
    author_comment_karma: int
    author_link_karma: int

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

